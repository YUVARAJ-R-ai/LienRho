"""CP4 entrypoint: real Tally export -> sanitized -> calibration report.

Run from backend/:
    uv run python -m app.data.calibrate \\
        --invoices path/to/invoices.xml \\
        --payments path/to/payments.xml \\
        [--customers path/to/customers.xml] \\
        [--out calibration-report.md]

Input is Tally's Collection XML (the same shape `connectors/tally/parser.py`
already handles) — export it from Tally's own UI (Gateway of Tally > company
> Alt+E or Display > Statutory Reports, whatever route gets a Collection
export) or by pointing the connector's HttpTallyTransport at a running
gateway and saving the raw response. No live gateway is required to run this;
a saved XML file is enough.

The report contains no customer names, IDs, or anything else identifying —
see `sanitize.py` for why `customer_id` needed remapping, not just
`customer_name`. It's safe to keep, share, or commit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.connectors.tally import parser
from app.data.calibration import build_report, compute_real_stats
from app.data.sanitize import sanitize_portfolio


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrate synthetic assumptions against real data")
    ap.add_argument("--invoices", type=Path, required=True, help="Tally Collection XML: bills")
    ap.add_argument("--payments", type=Path, required=True, help="Tally Collection XML: receipts")
    ap.add_argument("--customers", type=Path, help="Tally Collection XML: ledgers (optional)")
    ap.add_argument("--org-id", default="ORG-CALIBRATION")
    ap.add_argument("--out", type=Path, help="Write the report here (default: stdout only)")
    args = ap.parse_args()

    invoices_xml = args.invoices.read_text(encoding="utf-8", errors="replace")
    payments_xml = args.payments.read_text(encoding="utf-8", errors="replace")
    customers_xml = (
        args.customers.read_text(encoding="utf-8", errors="replace") if args.customers else None
    )

    invoices = parser.parse_invoices(invoices_xml, org_id=args.org_id)
    payments = parser.parse_payments(payments_xml, org_id=args.org_id)
    customers = parser.parse_customers(customers_xml, org_id=args.org_id) if customers_xml else []

    # A receipt voucher doesn't carry its bill's due date, so days_delayed is
    # None until joined against the matching invoice — the same join
    # TallyConnector.get_payments does, shared so this can't quietly compute
    # "delayed" differently than the model that trains on it.
    parser.join_payment_due_dates(payments, invoices)

    print(f"Parsed {len(invoices)} invoices, {len(payments)} payments, "
          f"{len(customers)} customer ledgers.", flush=True)

    sanitized = sanitize_portfolio(customers=customers, invoices=invoices, payments=payments)
    print(f"Pseudonymized {sanitized.customers_pseudonymized} distinct customers. "
          "No real name or ID appears past this point.", flush=True)

    stats = compute_real_stats(sanitized.payments)
    report = build_report(stats)
    rendered = report.render()

    print("\n" + rendered, flush=True)

    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")
        print(f"\nWritten to {args.out}", flush=True)

    return 0 if stats is not None else 1


if __name__ == "__main__":
    sys.exit(main())
