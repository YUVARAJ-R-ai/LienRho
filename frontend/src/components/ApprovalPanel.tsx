"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { ApprovalState, RecommendedAction } from "@/lib/types";

// The approval gate (FR-010, CON-06, BR-APPROVAL). Nothing sensitive — finance,
// escalation, outreach send — executes until a human explicitly approves.
// Rejecting must leave invoice state unchanged.
//
// State is local-only for now; wiring to the backend is part of the decision
// engine work. The UI contract (Approve/Reject, Send/Edit/Cancel) is fixed here
// so the endpoint can be built against it.

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
    body: "You can edit the drafted message before it goes out.",
  },
};

export function ApprovalPanel({
  action,
  initialState,
}: {
  action: RecommendedAction;
  initialState: ApprovalState;
}) {
  const [state, setState] = useState<ApprovalState>(initialState);
  const copy = actionCopy[action];

  if (state === "APPROVED") {
    return (
      <Alert className="border-emerald-200 bg-emerald-50">
        <AlertDescription className="text-emerald-800">
          Approved. {action === "FOLLOW_UP" ? "Reminder queued." : "Document generated."}
        </AlertDescription>
      </Alert>
    );
  }

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

  return (
    <Card className="border-amber-200 bg-amber-50/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{copy.title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{copy.body}</p>
        <div className="flex gap-2">
          <Button onClick={() => setState("APPROVED")}>
            {action === "FOLLOW_UP" ? "Send" : "Approve"}
          </Button>
          {action === "FOLLOW_UP" && (
            <Button variant="outline" disabled>
              Edit
            </Button>
          )}
          <Button variant="outline" onClick={() => setState("REJECTED")}>
            {action === "FOLLOW_UP" ? "Cancel" : "Reject"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
