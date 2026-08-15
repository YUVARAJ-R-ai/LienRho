"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CashForecast } from "@/lib/types";
import { formatLakhs, formatShortDate } from "@/lib/format";

// 30-day rolling cash forecast (FR-004). The threshold reference line is the
// point of the chart — the user needs to see *where* projected cash crosses it,
// not just the curve.

export function ForecastChart({ forecast }: { forecast: CashForecast }) {
  const data = forecast.points.map((p) => ({
    date: formatShortDate(p.date),
    cash: p.projectedCash,
  }));

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <defs>
            <linearGradient id="cashFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#4f46e5" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#4f46e5" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: "#64748b" }}
            tickLine={false}
            axisLine={{ stroke: "#e2e8f0" }}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 11, fill: "#64748b" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => formatLakhs(v)}
            width={64}
          />
          <Tooltip
            formatter={(value) => [formatLakhs(Number(value)), "Projected cash"]}
            contentStyle={{
              fontSize: 12,
              borderRadius: 8,
              border: "1px solid #e2e8f0",
            }}
          />
          <ReferenceLine
            y={forecast.cashThreshold}
            stroke="#dc2626"
            strokeDasharray="4 4"
            label={{
              value: `Threshold ${formatLakhs(forecast.cashThreshold)}`,
              position: "insideTopRight",
              fontSize: 11,
              fill: "#dc2626",
            }}
          />
          <Area
            type="monotone"
            dataKey="cash"
            stroke="#4f46e5"
            strokeWidth={2}
            fill="url(#cashFill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
