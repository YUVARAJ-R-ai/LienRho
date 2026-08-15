import Link from "next/link";
import { getActionQueue } from "@/lib/api";
import { formatLakhs } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ActionBadge, PriorityBadge } from "@/components/Badge";

// Approval queue (FR-010, CON-06). Everything here is in PENDING_APPROVAL —
// this screen exists so the human gate is a deliberate, reviewable step rather
// than something buried inside each invoice page.

export default async function ApprovalsPage() {
  const pending = (await getActionQueue()).filter(
    (item) => item.approvalState === "PENDING_APPROVAL",
  );

  const sensitive = pending.filter((i) => i.recommendedAction !== "FOLLOW_UP");
  const outreach = pending.filter((i) => i.recommendedAction === "FOLLOW_UP");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Approvals</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {pending.length} actions awaiting your decision.
        </p>
      </div>

      <Alert>
        <AlertDescription>
          No financing, escalation, or outreach is executed until you approve it.
          Rejecting leaves the invoice unchanged.
        </AlertDescription>
      </Alert>

      {[
        { heading: "Financing & escalation", items: sensitive },
        { heading: "Outreach", items: outreach },
      ].map(({ heading, items }) =>
        items.length === 0 ? null : (
          <section key={heading}>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              {heading}
              <span className="ml-2 font-normal normal-case">
                ({items.length})
              </span>
            </h2>
            <div className="space-y-3">
              {items.map((item) => (
                <Link
                  key={item.id}
                  href={`/invoice/${item.invoice.invoiceId}`}
                  className="block"
                >
                  <Card className="transition-shadow hover:shadow-md">
                    <CardContent className="flex items-center justify-between gap-4 p-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <PriorityBadge priority={item.priority} />
                          <span className="text-xs text-muted-foreground">
                            {item.invoice.invoiceId}
                          </span>
                        </div>
                        <p className="mt-1.5 flex items-baseline gap-2">
                          <span className="font-semibold tabular-nums">
                            {formatLakhs(item.invoice.invoiceAmount)}
                          </span>
                          <span className="truncate text-sm">
                            {item.invoice.customerName}
                          </span>
                        </p>
                        <p className="mt-0.5 text-sm text-muted-foreground">
                          {item.reason}
                        </p>
                      </div>
                      <ActionBadge action={item.recommendedAction} />
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          </section>
        ),
      )}
    </div>
  );
}
