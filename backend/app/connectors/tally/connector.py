"""TallyConnector — the AccountingConnector implementation for TallyPrime (#6).

Implements the interface and nothing else outside this module (NFR-006). The
canonical types it returns are the only thing the rest of the system sees.

The gateway has not been exercised against a live TallyPrime instance; see the
package docstring for what that means for ASM-01.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.canonical.models import CanonicalCustomer, CanonicalInvoice, CanonicalPayment
from app.connectors.base import AccountingConnector
from app.connectors.errors import ConnectorUnsupported
from app.connectors.tally import parser, requests
from app.connectors.tally.transport import HttpTallyTransport, TallyTransport


@dataclass(frozen=True)
class TallyConfig:
    """What this connector needs to know to reach one Tally company.

    `company` is the display name exactly as Tally shows it. Tally selects the
    company by that string, and a mismatch returns an empty collection rather
    than an error — which is why `get_invoices` returning nothing is worth
    checking against the company name before assuming the book is empty.
    """

    company: str
    url: str = "http://localhost:9000"
    # How far back to read. Payment history feeds the model's per-customer delay
    # statistics, so this wants to be generous; a year of history is the
    # smallest window that gives a seasonal feature anything to work with.
    history_days: int = 365
    timeout_s: float = 30.0


class TallyConnector(AccountingConnector):
    def __init__(
        self,
        config: TallyConfig,
        *,
        transport: TallyTransport | None = None,
        as_of: date | None = None,
    ) -> None:
        self.config = config
        self._transport = transport or HttpTallyTransport(
            config.url, timeout_s=config.timeout_s
        )
        # Injectable so a test pins the window instead of it moving with the
        # calendar, which would make fixture-based assertions fail overnight.
        self._as_of = as_of

    @property
    def _today(self) -> date:
        # Local calendar date on purpose, not UTC. Tally runs on the user's own
        # machine and books vouchers against the local date; for an IST business
        # a UTC "today" is still yesterday until 05:30, which would drop a day
        # of invoices from the read window.
        return self._as_of or date.today()  # noqa: DTZ011

    @property
    def _window(self) -> tuple[date, date]:
        today = self._today
        return today - timedelta(days=self.config.history_days), today

    def get_customers(self, org_id: str) -> list[CanonicalCustomer]:
        xml = self._transport.send(requests.customers_request(self.config.company))
        return parser.parse_customers(xml, org_id=org_id)

    def get_invoices(self, org_id: str) -> list[CanonicalInvoice]:
        from_date, to_date = self._window
        xml = self._transport.send(
            requests.invoices_request(
                self.config.company, from_date=from_date, to_date=to_date
            )
        )
        return parser.parse_invoices(xml, org_id=org_id)

    def get_payments(self, org_id: str) -> list[CanonicalPayment]:
        """Receipts, with each one's due date filled in from its bill.

        A receipt voucher does not carry the bill's due date, and
        `days_delayed` is the single most important field the delay model
        trains on. Rather than leave it null, the bills are fetched and joined
        here — the alternative is a payment history where nothing is late.
        """
        from_date, to_date = self._window
        xml = self._transport.send(
            requests.payments_request(
                self.config.company, from_date=from_date, to_date=to_date
            )
        )
        payments = parser.parse_payments(xml, org_id=org_id)
        return parser.join_payment_due_dates(payments, self.get_invoices(org_id))

    def get_expenses(self, org_id: str) -> list[dict]:
        from_date, to_date = self._window
        xml = self._transport.send(
            requests.expenses_request(
                self.config.company, from_date=from_date, to_date=to_date
            )
        )
        return parser.parse_expenses(xml)

    def create_task(self, org_id: str, description: str) -> None:
        """Not supported: TallyPrime has no task or to-do entity.

        Raising rather than silently doing nothing. A caller that thinks it
        recorded a follow-up when nothing was recorded is worse off than one
        that gets an error, and LIENRHO's own action queue is where follow-ups
        live anyway (FR-009).
        """
        raise ConnectorUnsupported(
            "TallyPrime has no task entity; follow-ups live in the LIENRHO action queue."
        )
