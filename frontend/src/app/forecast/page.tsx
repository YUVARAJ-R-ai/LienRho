import Link from "next/link";
import { getCashForecast } from "@/lib/api";
import { formatLakhs, formatDate } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatCard } from "@/components/StatCard";
import { ForecastChart } from "@/components/ForecastChart";

// Cash forecast screen (FR-004, FR-015). Beyond the curve, the screen must name
// the invoices driving the shortfall, ranked by contribution — that's what makes
// the forecast actionable rather than just informative.

export default async function ForecastPage() {
  const forecast = await getCashForecast();
  const ranked = [...forecast.contributingInvoices].sort(
    (a, b) => b.contribution - a.contribution,
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Cash forecast</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          30-day rolling projection from current cash, expected inflows, and known
          expenses.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Cash threshold"
          value={formatLakhs(forecast.cashThreshold)}
          sublabel="Minimum operating buffer"
        />
        <StatCard
          label="Shortfall date"
          value={
            forecast.shortfallDate ? formatDate(forecast.shortfallDate) : "None"
          }
          sublabel={
            forecast.shortfallDate
              ? "Earliest threshold breach"
              : "No breach in 30 days"
          }
          tone={forecast.shortfallDate ? "danger" : "neutral"}
        />
        <StatCard
          label="Shortfall amount"
          value={
            forecast.shortfallAmount ? formatLakhs(forecast.shortfallAmount) : "—"
          }
          sublabel="Gap at breach point"
          tone={forecast.shortfallAmount ? "danger" : "neutral"}
        />
      </div>

      {forecast.shortfallDate && (
        <Alert className="border-red-200 bg-red-50">
          <AlertDescription className="text-red-800">
            Projected cash falls below the threshold on{" "}
            <strong>{formatDate(forecast.shortfallDate)}</strong>. Financing or
            accelerating the invoices below would close the gap.
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Projected cash position</CardTitle>
        </CardHeader>
        <CardContent>
          <ForecastChart forecast={forecast} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            Invoices contributing to the shortfall
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Invoice</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead className="text-right">Contribution</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ranked.map((row) => (
                <TableRow key={row.invoiceId}>
                  <TableCell>
                    <Link
                      href={`/invoice/${row.invoiceId}`}
                      className="font-medium underline-offset-4 hover:underline"
                    >
                      {row.invoiceId}
                    </Link>
                  </TableCell>
                  <TableCell>{row.customerName}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatLakhs(row.amount)}
                  </TableCell>
                  <TableCell className="text-right font-medium tabular-nums">
                    {formatLakhs(row.contribution)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
