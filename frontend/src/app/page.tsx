import { getActionQueue, getPortfolioSummary } from "@/lib/api";
import { formatLakhs, formatShortDate } from "@/lib/format";
import { StatCard } from "@/components/StatCard";
import { ActionQueueCard } from "@/components/ActionQueueCard";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { Priority } from "@/lib/types";

// The daily action queue — the screen the owner opens every morning (FR-009).
// Items are grouped by priority tier and ordered by descending invoice value
// within tier, per the FR-009 acceptance criteria.

const tierOrder: Priority[] = ["CRITICAL", "HIGH", "FOLLOW_UP"];

const tierHeadings: Record<Priority, string> = {
  CRITICAL: "Critical",
  HIGH: "High",
  FOLLOW_UP: "Follow Up",
};

export default async function ActionQueuePage() {
  const [queue, summary] = await Promise.all([
    getActionQueue(),
    getPortfolioSummary(),
  ]);

  const grouped = tierOrder.map((tier) => ({
    tier,
    items: queue
      .filter((item) => item.priority === tier)
      .sort((a, b) => b.invoice.invoiceAmount - a.invoice.invoiceAmount),
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          What should we do today?
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {queue.length} recommended actions across {summary.openInvoices} open
          invoices.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total receivables"
          value={formatLakhs(summary.totalReceivables)}
          sublabel={`${summary.openInvoices} open invoices`}
        />
        <StatCard
          label="At risk"
          value={formatLakhs(summary.atRisk)}
          sublabel="High predicted delay"
          tone="danger"
        />
        <StatCard
          label="Projected shortfall"
          value={
            summary.shortfallAmount ? formatLakhs(summary.shortfallAmount) : "—"
          }
          sublabel={
            summary.shortfallDate
              ? `by ${formatShortDate(summary.shortfallDate)}`
              : "No shortfall projected"
          }
          tone="danger"
        />
        <StatCard
          label="Awaiting approval"
          value={String(
            queue.filter((i) => i.approvalState === "PENDING_APPROVAL").length,
          )}
          sublabel="Nothing executes until you approve"
        />
      </div>

      {summary.shortfallDate && (
        <Alert className="border-red-200 bg-red-50">
          <AlertDescription className="text-red-800">
            Projected cash falls below threshold on{" "}
            <strong>{formatShortDate(summary.shortfallDate)}</strong>, short by{" "}
            <strong>
              {summary.shortfallAmount ? formatLakhs(summary.shortfallAmount) : ""}
            </strong>
            .
          </AlertDescription>
        </Alert>
      )}

      <div className="space-y-6">
        {grouped.map(({ tier, items }) =>
          items.length === 0 ? null : (
            <section key={tier}>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                {tierHeadings[tier]}
                <span className="ml-2 font-normal normal-case">
                  ({items.length})
                </span>
              </h2>
              <div className="space-y-3">
                {items.map((item) => (
                  <ActionQueueCard key={item.id} item={item} />
                ))}
              </div>
            </section>
          ),
        )}
      </div>
    </div>
  );
}
