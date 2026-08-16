import Link from "next/link";
import { notFound } from "next/navigation";
import { getArtifact, getInvestigation } from "@/lib/api";
import { formatFullCurrency, formatDate, formatPercent } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { DelayBucketBar } from "@/components/DelayBucketBar";
import { ActionBadge, FlagBadge } from "@/components/Badge";
import { ApprovalPanel } from "@/components/ApprovalPanel";
import { AuditTrail } from "@/components/AuditTrail";

// Invoice investigation screen (FR-003, FR-007, FR-010, NFR-008).
// A first-time user must be able to identify the recommended action and its top
// reason without extra explanation — so the recommendation and its reason lead,
// and the supporting evidence follows beneath.

export default async function InvoiceInvestigationPage({
  params,
}: {
  params: Promise<{ invoiceId: string }>;
}) {
  const { invoiceId } = await params;
  const data = await getInvestigation(invoiceId);

  if (!data) notFound();

  const { invoice, prediction, factors, rules, findings, auditTrail } = data;

  // Only meaningful once the action has been approved; returns null otherwise,
  // so an unapproved dossier still does not exist anywhere.
  const artifact =
    data.approvalState === "APPROVED" ? await getArtifact(invoiceId) : null;

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← Back to action queue
        </Link>
        <div className="mt-2 flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              {invoice.customerName}
            </h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {invoice.invoiceId} · {formatFullCurrency(invoice.invoiceAmount)} ·
              due {formatDate(invoice.dueDate)} · {invoice.daysOverdue} days
              overdue
            </p>
          </div>
          <ActionBadge action={data.recommendedAction} />
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Why this recommendation</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm">{data.reason}</p>
        </CardContent>
      </Card>

      <ApprovalPanel
        invoiceId={invoice.invoiceId}
        action={data.recommendedAction}
        initialState={data.approvalState}
        initialArtifact={artifact}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Payment delay prediction</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <DelayBucketBar prediction={prediction} />
            <Separator />
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Top contributing factors
              </p>
              <ul className="space-y-2">
                {factors.map((factor) => (
                  <li key={factor.label} className="flex gap-2 text-sm">
                    <span
                      className={
                        factor.direction === "increases_risk"
                          ? "text-red-600"
                          : "text-emerald-600"
                      }
                    >
                      {factor.direction === "increases_risk" ? "▲" : "▼"}
                    </span>
                    <span>
                      <span className="font-medium">{factor.label}</span>
                      <span className="text-muted-foreground">
                        {" "}
                        — {factor.detail}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              Statutory &amp; financing checks
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">
                  MSMED statutory flag
                </span>
                <FlagBadge
                  label={rules.statutoryFlag ? "Crossed" : "Not crossed"}
                  tone={rules.statutoryFlag ? "danger" : "neutral"}
                />
              </div>
              {rules.statutoryInterest !== null && (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-muted-foreground">
                    Statutory interest
                  </span>
                  <span className="font-medium tabular-nums">
                    {formatFullCurrency(rules.statutoryInterest)}
                  </span>
                </div>
              )}
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">TReDS eligibility</span>
                <FlagBadge
                  label={rules.tredsEligible ? "Eligible" : "Not eligible"}
                  tone={rules.tredsEligible ? "success" : "neutral"}
                />
              </div>
              {rules.tredsIneligibleReason && (
                <p className="text-xs text-muted-foreground">
                  {rules.tredsIneligibleReason}
                </p>
              )}
            </div>
            <p className="rounded bg-muted px-2 py-1.5 text-xs text-muted-foreground">
              Computed by deterministic rules functions, not the language model.
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Communication evidence</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <FlagBadge
              label={
                findings.paymentPromise
                  ? `Payment promised${findings.promisedDate ? ` ${formatDate(findings.promisedDate)}` : ""}`
                  : "No payment promise"
              }
              tone={findings.paymentPromise ? "success" : "neutral"}
            />
            <FlagBadge
              label={findings.disputeDetected ? "Dispute detected" : "No dispute"}
              tone={findings.disputeDetected ? "danger" : "neutral"}
            />
            <FlagBadge
              label={`Confidence ${formatPercent(findings.confidence)}`}
            />
          </div>
          <ul className="space-y-1.5">
            {findings.evidence.map((line, i) => (
              <li key={i} className="text-sm text-muted-foreground">
                · {line}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Audit trail</CardTitle>
        </CardHeader>
        <CardContent>
          <AuditTrail entries={auditTrail} />
        </CardContent>
      </Card>
    </div>
  );
}
