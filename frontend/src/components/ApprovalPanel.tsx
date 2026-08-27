"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { decideOnAction, getDraft } from "@/lib/client-api";
import type {
  ApprovalState,
  Artifact,
  RecommendedAction,
} from "@/lib/types";

// The approval gate (FR-010, CON-06, BR-APPROVAL). Nothing sensitive — finance,
// escalation, outreach send — executes until a human explicitly approves.
// Rejecting must leave invoice state unchanged.
//
// Approving generates the artifact the action produces (FR-011/012/013) and
// shows it here. That is the point of the gate: the user does not approve an
// abstraction, they approve something and then see exactly what it produced.

const actionCopy: Record<RecommendedAction, { title: string; body: string }> = {
  ESCALATE: {
    title: "Approve statutory escalation?",
    body: "Generates an MSMED dossier for manual filing. Nothing is filed automatically.",
  },
  FINANCE: {
    title: "Approve TReDS financing?",
    body: "Generates a mock TReDS submission. No live financial transaction occurs.",
  },
  FOLLOW_UP: {
    title: "Send reminder?",
    body: "Review and edit the drafted message below before it goes out.",
  },
};

export function ApprovalPanel({
  invoiceId,
  action,
  initialState,
  initialArtifact = null,
}: {
  invoiceId: string;
  action: RecommendedAction;
  initialState: ApprovalState;
  // Fetched server-side when the action was already approved, so a generated
  // dossier survives a page reload rather than living only in the tab that
  // approved it.
  initialArtifact?: Artifact | null;
}) {
  const [state, setState] = useState<ApprovalState>(initialState);
  const [artifact, setArtifact] = useState<Artifact | null>(initialArtifact);
  // The draft body is held separately from the artifact because the user edits
  // it. FR-011 requires the message stay editable right up until it is sent.
  const [draftBody, setDraftBody] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isReminder = action === "FOLLOW_UP";

  // Load the reminder up front. For the other two actions the artifact does not
  // exist until it is approved, but a reminder is what the user is deciding
  // *about* — asking them to approve a message they have not read would be the
  // same rubber-stamp the gate exists to prevent.
  useEffect(() => {
    if (!isReminder || state !== "PENDING_APPROVAL") return;
    let cancelled = false;

    getDraft(invoiceId)
      .then((draft) => {
        if (!cancelled) setDraftBody(draft.contentMarkdown);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load the draft reminder.");
      });

    return () => {
      cancelled = true;
    };
  }, [invoiceId, isReminder, state]);

  const decide = useCallback(
    async (approved: boolean) => {
      setBusy(true);
      setError(null);
      try {
        const result = await decideOnAction(invoiceId, approved);
        setState(result.approvalState);
        setArtifact(result.artifact);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Something went wrong.");
      } finally {
        setBusy(false);
      }
    },
    [invoiceId],
  );

  if (state === "REJECTED") {
    return (
      <Alert>
        <AlertDescription>
          Rejected — invoice state unchanged. The rejection is recorded in the
          audit trail.
        </AlertDescription>
      </Alert>
    );
  }

  if (state === "APPROVED") {
    return (
      <div className="space-y-4">
        <Alert className="border-emerald-200 bg-emerald-50">
          <AlertDescription className="text-emerald-800">
            Approved.{" "}
            {isReminder
              ? "Copy the message below into your mail or WhatsApp client."
              : "The document below was generated."}
          </AlertDescription>
        </Alert>
        {artifact && <ArtifactView artifact={artifact} />}
      </div>
    );
  }

  const copy = actionCopy[action];

  return (
    <Card className="border-amber-200 bg-amber-50/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{copy.title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{copy.body}</p>

        {isReminder && draftBody !== null && (
          <textarea
            value={draftBody}
            onChange={(e) => setDraftBody(e.target.value)}
            rows={12}
            aria-label="Draft reminder"
            className="w-full rounded-md border border-input bg-background p-3 font-mono text-xs leading-relaxed"
          />
        )}

        {error && (
          <Alert className="border-red-200 bg-red-50">
            <AlertDescription className="text-red-800">{error}</AlertDescription>
          </Alert>
        )}

        <div className="flex gap-2">
          <Button onClick={() => decide(true)} disabled={busy}>
            {busy ? "Working…" : isReminder ? "Send" : "Approve"}
          </Button>
          <Button
            variant="outline"
            onClick={() => decide(false)}
            disabled={busy}
          >
            {isReminder ? "Cancel" : "Reject"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ArtifactView({ artifact }: { artifact: Artifact }) {
  // Rendered as preformatted Markdown rather than through a Markdown renderer.
  // Adding one would be a new dependency for no gain here: a dossier headed for
  // a tribunal and a message about to be pasted into WhatsApp both need to show
  // exactly the characters that will be filed or sent, not a prettied version
  // of them.
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{artifact.title}</CardTitle>
      </CardHeader>
      <CardContent>
        <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded bg-muted p-4 font-mono text-xs leading-relaxed">
          {artifact.contentMarkdown}
        </pre>
      </CardContent>
    </Card>
  );
}
