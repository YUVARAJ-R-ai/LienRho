# LIENRHO frontend

Next.js (App Router) + TypeScript + Tailwind + shadcn/ui.

## Run

```bash
npm install
npm run dev      # http://localhost:3000
```

## Screens

| Route | Purpose |
|---|---|
| `/` | Daily action queue — the primary screen (FR-009) |
| `/invoice/[invoiceId]` | Investigation: prediction, factors, rule flags, evidence, audit trail, approval (FR-003, FR-007, FR-010) |
| `/forecast` | 30-day cash forecast + shortfall contributors (FR-004, FR-015) |
| `/approvals` | Everything awaiting a human decision (FR-010) |

## Data

All screens currently read from `src/lib/mockData.ts`, which follows the reference demo scenario in `prd.md` §37 (30 invoices, ₹42.6L receivables, ₹6.2L shortfall). Screens import the accessor functions (`getActionQueue()`, `getInvestigation()`, `getCashForecast()`) rather than the constants, so swapping in real API calls means changing only that module.

`src/lib/types.ts` mirrors the backend canonical model (`backend/app/canonical/models.py`) plus LIENRHO's derived types. Keep the two in sync.
