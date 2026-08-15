# Resume here

Start-of-session checklist. Everything runs from `~/Coding/Projects/LienRho`.

## 1. Push what's waiting

```bash
cd ~/Coding/Projects/LienRho
git log --oneline origin/main..HEAD     # see what's unpushed
git push origin main
git push --tags                          # checkpoint tags cp0-pipeline, cp1-investigator
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
uv run pytest -q                 # expect 142 passed
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

## Demo click path

The four showcase invoices, in the order that tells the story best:

| Step | Where | What to point at |
|---|---|---|
| 1 | `/` | Ranked queue, ₹42.6L across 30 invoices, tiers |
| 2 | `/invoice/INV-1023` | Credible promise found in WhatsApp; date extracted; softens to a reminder |
| 3 | `/invoice/INV-1042` | Customer wrote *"we will settle fully"* — system escalates anyway, 3 prior promises unkept |
| 4 | `/invoice/INV-1051` | Statutory threshold crossed **but** a quality dispute is open, so it declines to act |
| 5 | `/invoice/INV-1038` | TReDS-eligible, financed to close the shortfall |
| 6 | `/forecast` | Shortfall date + the invoices driving it |

## Where things stand

- Plan and cutoffs: [`docs/demo-checkpoints.md`](docs/demo-checkpoints.md)
- What's built vs. specified: [`docs/implementation-status.md`](docs/implementation-status.md)
- Model metrics and limits: [`docs/model-card.md`](docs/model-card.md)

**Blocking decision:** `OQ-02` — which LLM provider, and is a key available? The
Investigator ships deterministically so nothing is stalled today, but the
LLM Strategy agent (#13) needs it.

## Gotchas

- `git push --tags` is separate from `git push`. Tags are the fallback plan.
- The model artifact is gitignored — teammates need step 4 once.
- Auth is a stubbed `X-Org-Id` header. Don't expose this beyond localhost (#20).
- Approvals are in-memory and reset when the API restarts (#19).
