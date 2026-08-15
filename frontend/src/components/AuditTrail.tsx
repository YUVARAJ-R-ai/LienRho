import type { AuditEntry } from "@/lib/types";
import { FlagBadge } from "./Badge";

// FR-014/NFR-007: every recommendation must be traceable to the specific
// ML prediction, rule evaluation, and agent output that produced it — without
// digging through raw logs. The "who decided" column is what makes the
// deterministic-vs-LLM boundary (ADR-002) visible to the user.

// TOOL entries are the evidence for ADR-002 — each one names a deterministic
// function the agent called rather than computed itself. They're toned green
// alongside RULES so the "not model-generated" path is visually distinct from
// the ML prediction and the agent's judgement.
const decidedByTone: Record<AuditEntry["decidedBy"], "neutral" | "success"> = {
  ML: "neutral",
  RULES: "success",
  TOOL: "success",
  AGENT: "neutral",
  HUMAN: "neutral",
};

export function AuditTrail({ entries }: { entries: AuditEntry[] }) {
  return (
    <ol className="space-y-3">
      {entries.map((entry, i) => (
        <li key={i} className="relative border-l border-border pl-4">
          <span className="absolute -left-[3px] top-2 h-1.5 w-1.5 rounded-full bg-border" />
          <div className="flex flex-wrap items-center gap-2">
            <FlagBadge label={entry.decidedBy} tone={decidedByTone[entry.decidedBy]} />
            <span
              className={
                entry.decidedBy === "TOOL"
                  ? "font-mono text-sm font-medium"
                  : "text-sm font-medium"
              }
            >
              {entry.what}
            </span>
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">{entry.why}</p>
          <p className="mt-0.5 text-xs text-muted-foreground/70">
            {new Date(entry.timestamp).toLocaleString("en-IN")}
          </p>
        </li>
      ))}
    </ol>
  );
}
