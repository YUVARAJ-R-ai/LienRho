import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import type { ActionQueueItem } from "@/lib/types";
import { formatLakhs } from "@/lib/format";
import { ActionBadge, PriorityBadge } from "./Badge";
import { DelayBucketBar } from "./DelayBucketBar";

// One row of the daily action queue (FR-009). Every card shows amount, customer,
// reason, and recommended action — that combination is the acceptance criterion
// and what makes the queue explainable without opening the invoice (NFR-008).

export function ActionQueueCard({ item }: { item: ActionQueueItem }) {
  const { invoice } = item;

  return (
    <Link href={`/invoice/${invoice.invoiceId}`} className="block">
      <Card className="transition-shadow hover:shadow-md">
        <CardContent className="p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <PriorityBadge priority={item.priority} />
                <span className="text-xs text-muted-foreground">
                  {invoice.invoiceId}
                </span>
              </div>
              <p className="mt-2 flex items-baseline gap-2">
                <span className="text-xl font-semibold tabular-nums">
                  {formatLakhs(invoice.invoiceAmount)}
                </span>
                <span className="truncate text-sm text-foreground/80">
                  {invoice.customerName}
                </span>
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{item.reason}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {invoice.daysOverdue} days overdue
              </p>
            </div>
            <div className="shrink-0">
              <ActionBadge action={item.recommendedAction} />
            </div>
          </div>
          <div className="mt-3">
            <DelayBucketBar prediction={item.prediction} showLegend={false} />
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
