# Resume here

Start-of-session checklist. Paths below are written relative to the repo root — substitute wherever your checkout lives.

## 1. Push what's waiting

```bash
cd <repo root>
git log --oneline origin/main..HEAD     # see what's unpushed
git push origin main
git push --tags                          # tags: cp0-pipeline, cp1-investigator, cp2-tool-boundary
```

## 2. Bring the stack up

```bash
# Postgres (only if the container isn't already up)
cd backend
docker compose up -d
uv run alembic upgrade head              # migrations, including auth + sync tables
uv run python -m app.auth.seed           # demo org + login; idempotent, safe to re-run

# Backend API — detached, low priority
./run-dev.sh start        # log: /tmp/lienrho-api.log
./run-dev.sh status
./run-dev.sh stop

# Frontend (separate terminal)
cd frontend
npm run dev               # http://localhost:3000
```

Open **http://localhost:3000**. You will land on `/login` — every screen is
behind auth now (#20). Sign in with **`demo@lienrho.local` / `lienrho-demo`**,
created by step 2's seed. The backend must be running; the screens read from it.

## 3. Verify nothing broke

```bash
cd backend
uv run pytest -q                 # expect 326 passed (no database needed)
uv run ruff check .

cd ../frontend
npx tsc --noEmit && npm run lint && npm run build
```

## 4. Retrain the model (only if you changed features or the generator)

```bash
cd backend
uv run python -m app.ml_core.train              # CUDA, falls back to CPU
uv run python -m app.ml_core.train --cpu        # force CPU
```

Exits non-zero if the NFR-005 gate fails. Expect ROC-AUC ≈ 0.834, ECE ≈ 0.044.
The artifact is gitignored, so **every teammate must run this once** — the API
falls back to rule-only recommendations without it.

## Demo

Full click path, narration, and what to do if something breaks:
[`docs/demo-script.md`](docs/demo-script.md). Target 3–4 minutes.

Short version — the four showcase invoices in story order:

| | Where | Beat |
|---|---|---|
| 0 | `/login` | Sign in — do this *before* presenting, not on stage |
| 1 | `/` | Ranked queue, ₹42.6L across 30 invoices |
| 2 | `/invoice/INV-1023` | Promise found in WhatsApp, date extracted → reminder |
| 3 | `/invoice/INV-1042` | Same words, worthless promise → escalates; `TOOL` trace shows `calculate_interest() → 5840.07` |
| 4 | `/invoice/INV-1051` | Dispute open → declines to act |
| 5 | `/invoice/INV-1038` | TReDS-eligible → finances to close the shortfall |
| 6 | `/forecast` | Shortfall date + the invoices driving it |

## CP4 tool — ready, waiting on real Tally data

```bash
cd backend
uv run python -m app.data.calibrate \
  --invoices path/to/invoices.xml --payments path/to/payments.xml \
  [--customers path/to/customers.xml] [--out calibration-report.md]
```

Takes a saved Tally Collection XML export (no live gateway needed). Every
customer name/ID is pseudonymized before anything is computed or printed —
safe to share or commit the output. Verified end-to-end against
`tests/fixtures/tally/*.xml`; 22 tests in `test_sanitize.py` +
`test_calibration.py`.

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

**CP3 is done** — draft reminder, mock TReDS submission, and MSMED dossier all
ship (#15). Issues #13, #15, #19, #20 and #21 are closed; #6 is built but stays
open until a live TallyPrime has answered it (`ASM-01`).

**What is actually left:** `ASM-01` (the Tally spike), `OQ-02` (pick a provider
and flip `llm_enabled`), NFR-008's informal user test, and the frontend has no
tests. See [`implementation-status.md`](docs/implementation-status.md).

## Gotchas

- `git push --tags` is separate from `git push`. Tags are the fallback plan.
- The model artifact is gitignored — teammates need step 4 once. Without it the
  API serves rule-only recommendations with **empty** delay predictions rather
  than failing, so a forgotten step 4 looks like a working app with a dead ML
  layer.
- Every `/api/*` route needs a bearer token (#20). Seed a login in step 2; the
  frontend keeps it in an httpOnly cookie, so signing in through the UI is the
  only setup needed.
- Approvals and the audit trail are durable now (#19). If `/health` reports
  `auditStore.durable: false`, the API could not reach Postgres and is serving
  from memory — decisions will vanish on restart.
- `uv run pytest` needs no database, but `test_sync.py` and the Postgres half of
  `test_approval_store.py` skip without one. A green run is not proof those
  paths work.
