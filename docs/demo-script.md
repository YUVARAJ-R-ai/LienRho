# Demo script

Target: **3–4 minutes**. Rehearse aloud three times and time it (CP5).

Setup before you present: backend + frontend running, browser on `http://localhost:3000`, and the four showcase invoices open in tabs so no step depends on typing a URL correctly under pressure.

---

## 0. The hook (20s) — before touching the screen

> "An MSME owner opens Tally every morning and sees ₹42.6 lakh outstanding across 30 invoices. That number is true and completely useless. It doesn't say which of those will actually be paid, when, or what to do about any of it. So the owner becomes the glue — cross-referencing Tally, the bank balance, WhatsApp threads, and the MSMED Act by hand, every single day.
>
> LIENRHO sits on top of the accounting system they already use and answers one question: **what should this business do today?**"

Don't open with the architecture. Open with the owner.

## 1. The action queue (30s) — `/`

> "This is the whole product. Thirty invoices ranked into Critical, High, and Follow Up — not by how overdue they are, but by what actually deserves attention."

Point at the header figures: ₹42.6L receivables, the at-risk total, the projected shortfall date.

> "Every row already carries its recommendation and the reason for it. The owner doesn't open anything to triage."

## 2. A promise worth trusting (40s) — `/invoice/INV-1023`

> "₹4.8 lakh, 17 days overdue. Most systems would fire off a dunning notice."

Scroll to **Communication evidence**.

> "But there's a WhatsApp thread nobody logged, and the agent read it: *'We will clear this by Friday, payment is in process.'* It extracted the date — 21st August. Four-year customer, no disputes ever."

Point at the recommendation.

> "So it recommends a gentle reminder, not escalation. Chasing this customer hard would cost more than it collects."

## 3. A promise worth nothing (50s) — `/invoice/INV-1042` ← **the important one**

> "Same situation on paper. Overdue invoice, and the customer has *also* promised to pay — *'we will settle fully.'*"

Pause on that line.

> "Read those two sentences side by side and they're nearly identical. A keyword matcher marks both 'payment promised' and softens both."

Point at the evidence.

> "This customer has promised three times and paid zero. So the system refuses to believe the fourth — and escalates."

Then scroll to the **audit trail**.

> "And here's the part that matters for a finance product. The statutory interest is ₹5,840. The agent did **not** calculate that."

Point at the `TOOL` entries.

> "`calculate_interest() → 5840.07`. Every statutory number in this system comes from a deterministic Python function, and every call is recorded. The agent chooses *what to do*. It never touches the arithmetic — because that figure goes into a legal filing."

## 4. Knowing when not to act (30s) — `/invoice/INV-1051`

> "Sunrise Textiles. Past the statutory threshold, TReDS-eligible — on paper this is a slam dunk for escalation."

Point at the dispute evidence.

> "Except the customer raised a quality objection — 15% shade variation, with QC photographs. So the system declines to escalate *or* finance until a human resolves it. Escalating a disputed invoice damages the relationship and weakens the claim."

> "Any system can act. Knowing when not to is the harder problem."

## 5. Financing (25s) — `/invoice/INV-1038`

> "Global Retail, ₹3.2 lakh, not yet due, TReDS-eligible. Nothing is wrong here — this invoice isn't a problem, it's a *solution*. There's a cash shortfall coming, and discounting this closes it."

## 6. The forecast (25s) — `/forecast`

> "Thirty-day rolling projection. Each invoice contributes its value weighted by the model's predicted probability that it's actually landed by that day — not by assuming everyone pays on time."

Point at the threshold crossing and the contributor table.

> "Here's the date cash goes below the floor, and here are the specific invoices driving it, ranked. That's what turns a warning into an action."

## 7. Close (20s)

> "Classical ML for prediction. Deterministic Python for anything statutory. Agents for judgement over unstructured evidence. Human approval before anything irreversible. Every recommendation traceable to the exact function that produced it.
>
> Not a chatbot on top of a ledger — a decision layer with a paper trail."

---

## Say this accurately

The tool boundary, the recording, and the trace are **real**. The *selection* in this demo is rule-based because `llm_enabled` is off — the LLM agents (`LLMInvestigator`, `LLMStrategist`) are implemented and swap in via `settings.llm_enabled`, but the deterministic path remains the production fallback.

- ✅ "Here's the boundary the agent works through, and every number traces to a named function."
- ✅ "The agent chose to escalate; it never calculated the interest."
- ✅ "The LLM agents are implemented and tested against a mock — flipping `llm_enabled` switches to model-driven selection once a provider is configured."

The architecture claim is fully true today. Don't oversell the model and hand a judge an easy question you can't answer.

## Numbers you should know cold

| | |
|---|---|
| Portfolio | ₹42.6L across 30 invoices |
| Model | ROC-AUC **0.834**, ECE **0.031** (gate: ≥0.75, ≤0.10) |
| Bucket accuracy | 62.3% vs 25% four-class baseline |
| Statutory interest, INV-1042 | ₹5,840.07 |
| MSMED threshold | 45 days from the appointed day |
| Tests | 157 passing |

**If asked "isn't 0.834 low?"** — that's the honest number. The first generator leaked the label and would have scored near-perfectly while learning nothing; delays now come from a multi-factor latent process and customer statistics are derived from observed history. See [`model-card.md`](model-card.md).

**If asked about real data** — trained on synthetic (`ASM-02`). The generator is calibrated to plausible MSME behaviour; metrics show the pipeline learns real structure, they are not a field-performance claim.

## If something breaks

| Symptom | Cause | Do this |
|---|---|---|
| Predictions all zero / flat | Model artifact missing | `uv run python -m app.ml_core.train` — it's gitignored |
| Screens error or hang | Backend down | `cd backend && ./run-dev.sh start`, check `/tmp/lienrho-api.log` |
| Approvals reset | In-memory by design (#19) | Don't demo approval persistence |
| A page misbehaves | — | Fall back to a tagged checkpoint: `git checkout cp2-tool-boundary` |

Have `/` and `/invoice/INV-1042` open in tabs before you start. If live navigation fails, the two screens that carry the story are already loaded.
