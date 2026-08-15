import { Badge } from "@/components/ui/badge";
import type { Priority, RecommendedAction } from "@/lib/types";

// Domain-specific badge wrappers over shadcn's Badge, so priority/action colour
// mapping lives in one place instead of being repeated at every call site.

const priorityStyles: Record<Priority, string> = {
  CRITICAL: "border-transparent bg-red-100 text-red-800 hover:bg-red-100",
  HIGH: "border-transparent bg-amber-100 text-amber-900 hover:bg-amber-100",
  FOLLOW_UP: "border-transparent bg-slate-100 text-slate-700 hover:bg-slate-100",
};

const priorityLabels: Record<Priority, string> = {
  CRITICAL: "Critical",
  HIGH: "High",
  FOLLOW_UP: "Follow Up",
};

const actionStyles: Record<RecommendedAction, string> = {
  ESCALATE: "border-transparent bg-red-600 text-white hover:bg-red-600",
  FINANCE: "border-transparent bg-indigo-600 text-white hover:bg-indigo-600",
  FOLLOW_UP: "border-transparent bg-slate-800 text-white hover:bg-slate-800",
};

const actionLabels: Record<RecommendedAction, string> = {
  ESCALATE: "Escalate",
  FINANCE: "Finance",
  FOLLOW_UP: "Send reminder",
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  return <Badge className={priorityStyles[priority]}>{priorityLabels[priority]}</Badge>;
}

export function ActionBadge({ action }: { action: RecommendedAction }) {
  return <Badge className={actionStyles[action]}>{actionLabels[action]}</Badge>;
}

export function FlagBadge({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "danger" | "success";
}) {
  const tones = {
    neutral: "border-transparent bg-slate-100 text-slate-700 hover:bg-slate-100",
    danger: "border-transparent bg-red-100 text-red-800 hover:bg-red-100",
    success: "border-transparent bg-emerald-100 text-emerald-800 hover:bg-emerald-100",
  };
  return (
    <Badge variant="secondary" className={tones[tone]}>
      {label}
    </Badge>
  );
}
