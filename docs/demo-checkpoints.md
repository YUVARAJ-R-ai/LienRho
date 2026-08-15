# Demo checkpoints

**Principle:** every checkpoint ends with a complete sentence in the pitch, not a half-built feature. If we run out of time at any point, we demo the last frozen checkpoint and nothing looks unfinished.

Two rules make this work:

1. **Tag every checkpoint** (`git tag cp1-agents`). A checkpoint you can't return to isn't a checkpoint.
2. **Pre-cache agent output for the three showcase invoices.** A live LLM call in the demo path is a network dependency standing in front of judges. Cache INV-1023 / INV-1038 / INV-1042; let everything else call live.

| CP | New sentence in the pitch | Cutoff | If it slips |
|---|---|---|---|
| 0 | "Tally says you're owed ₹42.6L. We say what to do today." | ✅ done | — |
| 1 | "It reads the conversations too." | Sun midday | Demo CP0 |
| 2 | "The LLM picks strategy but never touches the numbers." | Sun night | Demo CP1 |
| 3 | "And here's the actual dossier — after you approve." | Mon afternoon | Demo CP2 |
| 4 | "Validated against 10 years of real invoices." | Mon 6pm hard stop | Skip entirely |
| 5 | Freeze + rehearse | Mon night | — |

## CP0 — Prediction and prioritization ✅

**Status:** done. Tag `cp0-pipeline`.

**Click path:** action queue → three priority tiers → open INV-1042 → statutory flag, ₹5,840 interest, four-bucket delay distribution, ML/Rules/Agent audit trail → forecast screen → shortfall date and contributing invoices.

**What it proves:** the pipeline is real. ML predictions, deterministic statutory checks, a probabilistic forecast, and a ranked queue, each traceable to what produced it.

## CP1 — Communication intelligence

**Delivers:** synthetic WhatsApp/email threads + the Receivables Investigator agent (FR-007, issue #12).

**Click path:** open INV-1023 → the agent found "we'll clear this by Friday" in a thread nobody logged → recommendation softens to a relationship-preserving follow-up.

**Design note:** include at least one customer whose promises are *unreliable*, so the agent's finding and the ML prediction disagree. That contrast is the most interesting thing on the screen — it shows the system weighing two sources rather than parroting one.

**Slots in cleanly:** `decide_action()` already takes `payment_promise` and `dispute_detected`; nothing populates them yet. The agent fills that seam without a refactor.

**Note:** the synthetic threads need the same anti-leakage discipline as the delay data (see ADR-004). A thread should not be a restatement of the label.

## CP2 — The defensibility story

**Delivers:** Recovery Strategy as a LangGraph agent calling the rules engine as tools (FR-008, issue #13).

**Click path:** show the trace — the LLM selected ESCALATE, but the ₹5,840 came from `calculate_interest()`, not the model.

**Why it matters most:** this is ADR-002 made visible. For a finance audience it's the strongest single moment in the demo — the answer to "how do I know it didn't hallucinate the number."

**Keep the fallback.** `decide_action()` stays as the deterministic path so a dead API key degrades the demo instead of ending it.

## CP3 — Closing the loop

**Delivers:** draft reminder, mock TReDS submission, MSMED dossier (FR-011/012/013, issue #15).

**Click path:** approve an action → the generated artifact appears.

**Why:** it pays off the approval gate that's already built, and turns "the system recommends" into "the system produced this."

## CP4 — Real-data calibration *(optional, cuttable)*

**Not retraining.** Compute real base rates and the actual delay distribution from sanitized invoices, then either tune the generator's profile constants to match or put the comparison on a slide.

**Hard stop 6pm Monday.** Retraining the night before a demo is the highest-risk thing on this list; calibration is the version that cannot break anything.

## CP5 — Freeze

No new features. Tag, then rehearse the click path three times out loud and time it.

## Parallel split

| | Sat night → Sun | Sun → Mon |
|---|---|---|
| Agents | Synthetic threads → Investigator | Strategy agent + LangGraph trace |
| Backend | — | Outreach / TReDS mock / dossier |
| Frontend | Surface agent findings (shape already reserved) | Demo polish, dossier view |
| ML | Chase the API key | Real-data calibration, rehearsal |

## Blockers

- **LLM provider and API key (`OQ-02`)** — hard blocker on CP2 and most of CP1. Nothing agent-shaped starts without it.
- **Outreach delivery (`OQ-01`)** — defaulting to drafted-in-UI. Live WhatsApp/SMTP is out of scope for this window.
- **Tally connector (#6)** — recommended cut. `ASM-01` flags that Tally's HTTP/XML gateway needs a spike to confirm it's even reachable, and finding out it isn't on Monday would be the worst possible timing. The connector interface exists and `_load_portfolio()` is a one-function swap, which is enough to tell the integration story.
