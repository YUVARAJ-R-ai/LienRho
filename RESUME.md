# Resume here

Start-of-session checklist. Everything runs from `~/Coding/Projects/LienRho`.

## 1. Push what's waiting

```bash
cd ~/Coding/Projects/LienRho
git log --oneline origin/main..HEAD     # see what's unpushed
git push origin main
git push --tags                          # tags: cp0-pipeline, cp1-investigator, cp2-tool-boundary
```

## 2. Bring the stack up

```bash
# Postgres (only if the container isn't already up)
cd ~/Coding/Projects/LienRho/backend
docker compose up -d

# Backend API — detached, low priority, capped to 12 cores
./run-dev.sh start        # log: /tmp/lienrho-api.log
./run-dev.sh status
./run-dev.sh stop

# Frontend (separate terminal)
cd ~/Coding/Projects/LienRho/frontend
npm run dev               # http://localhost:3000
```

Open **http://localhost:3000**. The backend must be running — the screens read from it.

## 3. Verify nothing broke

```bash
cd ~/Coding/Projects/LienRho/backend
uv run pytest -q                 # expect 157 passed
uv run ruff check .

cd ../frontend
npx tsc --noEmit && npm run lint && npm run build
```

## 4. Retrain the model (only if you changed features or the generator)

```bash
cd ~/Coding/Projects/LienRho/backend
uv run python -m app.ml_core.train              # CUDA, falls back to CPU
uv run python -m app.ml_core.train --cpu        # force CPU
```

Exits non-zero if the NFR-005 gate fails. Expect ROC-AUC ≈ 0.834, ECE ≈ 0.031.
The artifact is gitignored, so **every teammate must run this once** — the API
falls back to rule-only recommendations without it.

## Demo

Full click path, narration, and what to do if something breaks:
[`docs/demo-script.md`](docs/demo-script.md). Target 3–4 minutes.

Short version — the four showcase invoices in story order:

| | Where | Beat |
|---|---|---|
| 1 | `/` | Ranked queue, ₹42.6L across 30 invoices |
| 2 | `/invoice/INV-1023` | Promise found in WhatsApp, date extracted → reminder |
| 3 | `/invoice/INV-1042` | Same words, worthless promise → escalates; `TOOL` trace shows `calculate_interest() → 5840.07` |
| 4 | `/invoice/INV-1051` | Dispute open → declines to act |
| 5 | `/invoice/INV-1038` | TReDS-eligible → finances to close the shortfall |
| 6 | `/forecast` | Shortfall date + the invoices driving it |

## Where things stand

- Plan and cutoffs: [`docs/demo-checkpoints.md`](docs/demo-checkpoints.md)
- What's built vs. specified: [`docs/implementation-status.md`](docs/implementation-status.md)
- Model metrics and limits: [`docs/model-card.md`](docs/model-card.md)

**Blocking decision:** `OQ-02` — which LLM provider, and is a key available?
Both agents ship deterministically behind the same interfaces, so nothing is
stalled today. Swapping either to an LLM is one class (`LLMInvestigator`,
`LLMStrategist`) — the tool boundary, the recording, and the trace are already
what the model will use.

**Say it accurately in the demo:** the tool-call trace is real and the
deterministic boundary genuinely holds — but the *selection* is rule-based right
now, not model-driven. "Here's the boundary the agent works through" is true;
"an LLM chose this" is not, yet.

**Next up — CP3** (`docs/demo-checkpoints.md`): draft reminder, mock TReDS
submission, MSMED dossier (#15). Fully deterministic, no API key needed, and it
pays off the approval gate that's already built.

## Gotchas

- `git push --tags` is separate from `git push`. Tags are the fallback plan.
- The model artifact is gitignored — teammates need step 4 once.
- Auth is a stubbed `X-Org-Id` header. Don't expose this beyond localhost (#20).
- Approvals are in-memory and reset when the API restarts (#19).
