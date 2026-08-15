import type { DelayPrediction } from "@/lib/types";
import { formatPercent } from "@/lib/format";

// Renders the XGBoost 4-bucket delay distribution (FR-002) as a stacked bar.
// Colour darkens with severity so the shape is readable at a glance.

const buckets = [
  { key: "bucket_0_15", label: "0–15d", color: "bg-emerald-500" },
  { key: "bucket_16_30", label: "16–30d", color: "bg-amber-400" },
  { key: "bucket_31_45", label: "31–45d", color: "bg-orange-500" },
  { key: "bucket_over_45", label: ">45d", color: "bg-red-600" },
] as const;

export function DelayBucketBar({
  prediction,
  showLegend = true,
}: {
  prediction: DelayPrediction;
  showLegend?: boolean;
}) {
  return (
    <div className="space-y-2">
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
        {buckets.map(({ key, color }) => {
          const value = prediction[key];
          if (value <= 0) return null;
          return (
            <div
              key={key}
              className={color}
              style={{ width: `${value * 100}%` }}
              title={`${key}: ${formatPercent(value)}`}
            />
          );
        })}
      </div>
      {showLegend && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
          {buckets.map(({ key, label, color }) => (
            <span key={key} className="inline-flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${color}`} />
              {label} {formatPercent(prediction[key])}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
