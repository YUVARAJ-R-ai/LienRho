# Demo checkpoints

**Principle:** every checkpoint ends with a complete sentence in the pitch, not a half-built feature. If we run out of time at any point, we demo the last frozen checkpoint and nothing looks unfinished.

Two rules make this work:

1. **Tag every checkpoint** (`git tag cp1-agents`). A checkpoint you can't return to isn't a checkpoint.
2. **Pre-cache agent output for the three showcase invoices.** A live LLM call in the demo path is a network dependency standing in front of judges. Cache INV-1023 / INV-1038 / INV-1042; let everything else call live.

| CP | New sentence in the pitch | Cutoff | If it slips |
|---|---|---|---|
| 0 | "Tally says you're owed ₹42.6L. We say what to do today." | ✅ done | — |
| 1 | "It reads the conversations too." | ✅ done | — |
| 2 | "The LLM picks strategy but never touches the numbers." | ✅ done | — |
| 3 | "And here's the actual dossier — after you approve." | ✅ done | — |
| 4 | "Validated against 10 years of real invoices." | Mon 6pm hard stop | Skip entirely |
| 5 | Freeze + rehearse | Mon night | — |

## CP0 — Prediction and prioritization ✅

**Status:** done. Tag `cp0-pipeline`.

**Click path:** action queue → three priority tiers → open INV-1042 → statutory flag, ₹5,840 interest, four-bucket delay distribution, ML/Rules/Agent audit trail → forecast screen → shortfall date and contributing invoices.

**What it proves:** the pipeline is real. ML predictions, deterministic statutory checks, a probabilistic forecast, and a ranked queue, each traceable to what produced it.

## CP1 — Communication intelligence ✅

**Status:** done. Tag `cp1-investigator`.

**Delivers:** synthetic WhatsApp/email threads + the Receivables Investigator (FR-007, issue #12), running deterministically so it did not wait on `OQ-02`.

**The strongest moment:** open INV-1042. The customer wrote *"we will settle fully"* — and the system escalates anyway, because they have promised three times and paid none. The literal text of a credible promise and a worthless one are nearly identical; showing the system tell them apart is the clearest argument that reading the threads is worth anything.

**Second strongest:** INV-1051. Statutory threshold crossed and TReDS-eligible on paper, but a quality dispute is on file, so the system *declines to escalate or finance*. A system that only ever acts is easy to build; one that knows when not to is the harder claim.

**Click path:** open INV-1023 → the agent found "we'll clear this by Friday" in a thread nobody logged → recommendation softens to a relationship-preserving follow-up.

**Design note:** include at least one customer whose promises are *unreliable*, so the agent's finding and the ML prediction disagree. That contrast is the most interesting thing on the screen — it shows the system weighing two sources rather than parroting one.

**Slots in cleanly:** `decide_action()` already takes `payment_promise` and `dispute_detected`; nothing populates them yet. The agent fills that seam without a refactor.

**Note:** the synthetic threads need the same anti-leakage discipline as the delay data (see ADR-004). A thread should not be a restatement of the label.

## CP2 — The defensibility story ✅

**Status:** done. Tag `cp2-tool-boundary`.

**Delivers:** the agent tool boundary (`agents/tools.py`) and the Recovery Strategy agent over it (`agents/strategy.py`), with every call recorded and surfaced.

**Click path:** open INV-1042 → scroll to the audit trail → the `TOOL` entries read `check_msmed_threshold() → statutory_flag=True, days_overdue=51` and `calculate_interest() → interest=5840.07`.

**The line to say:** *"the agent chose to escalate — but it never calculated that ₹5,840. It called this function, and here's the call."*

**Why it matters most:** ADR-002 stops being an assertion and becomes something a judge can read off the screen. For a finance audience it's the answer to "how do I know it didn't hallucinate the number."

**What's deterministic today:** `RuleBasedStrategist` makes the selection. The tool boundary, the recording, and the trace are real and are what the LLM will use unchanged — `LLMStrategist` swaps one class. So the defensibility story is *already true*; the model just isn't the one exercising it yet. Say it that way rather than implying an LLM is running.

**Remaining for #13:** bind `TOOL_SCHEMAS` to a LangGraph node, loop until the model stops requesting tools, validate the output, and fall through to `RuleBasedStrategist` on any failure.

## CP3 — Closing the loop ✅

**Status:** done (#15, commit 31acafd). Not yet tagged — tag it before the demo, the fallback plan depends on it.

**Delivers:** draft reminder, mock TReDS submission, MSMED dossier (FR-011/012/013, issue #15).

**Click path:** approve an action → the generated artifact appears.

**Why:** it pays off the approval gate that's already built, and turns "the system recommends" into "the system produced this."

## CP4 — Real-data calibration *(optional, cuttable)*

**Not retraining.** Compute real base rates and the actual delay distribution from sanitized invoices, then either tune the generator's profile constants to match or put the comparison on a slide.

**Hard stop 6pm Monday.** Retraining the night before a demo is the highest-risk thing on this list; calibration is the version that cannot break anything.

## CP5 — Freeze

No new features. Tag, then rehearse [`demo-script.md`](demo-script.md) three times out loud and time it. Target 3–4 minutes.

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
- **Tally connector (#6)** — *no longer a cut, but still not proven.* `TallyConnector` is built against the documented XML gateway and covered by fixture-based tests, and `POST /api/sync` persists a sync to the canonical store (FR-001). `ASM-01` remains open: no live TallyPrime has answered it. Demo the sync from the synthetic connector, which exercises the identical path — and say "the connector is written and the ingest path is real; we have not had a Tally instance to point it at" rather than implying it has run against one.
