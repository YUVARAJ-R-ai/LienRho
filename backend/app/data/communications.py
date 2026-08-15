"""Synthetic customer communication threads (FR-007, ASM-03).

The Receivables Investigator reads WhatsApp/email history to extract structured
findings. No real correspondence exists, so these threads stand in.

Three things make this data worth having rather than decorative:

1. **Promises are not uniformly credible.** ABC Logistics promises and pays;
   Apex Trading has promised three times and paid none of them. A naive keyword
   match reads both as "payment promised" and gets Apex badly wrong. Modelling
   promise *reliability* is the whole reason this layer earns its place.
2. **Some signals contradict the ML prediction.** That disagreement is the most
   informative thing on the investigation screen — it shows the system weighing
   two sources rather than restating one.
3. **The threads don't restate the label.** Nobody writes "this invoice will be
   paid in 47 days". They write ambiguous, hedged, human things. Same discipline
   as ADR-004: if the text simply encoded the answer, the agent would be
   theatre.

Language mirrors Indian SME business correspondence — English with occasional
Hindi/transliterated interjections, WhatsApp brevity, email formality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from app.data.synthetic import AS_OF


class Channel(StrEnum):
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"


class Direction(StrEnum):
    # From us to the customer.
    OUTBOUND = "OUTBOUND"
    # From the customer to us — the only messages that carry evidence.
    INBOUND = "INBOUND"


@dataclass(frozen=True)
class Message:
    sent_on: date
    channel: Channel
    direction: Direction
    body: str


@dataclass
class CommunicationThread:
    """All correspondence tied to one invoice."""

    invoice_id: str
    customer_id: str
    messages: list[Message] = field(default_factory=list)

    @property
    def inbound(self) -> list[Message]:
        return [m for m in self.messages if m.direction is Direction.INBOUND]

    @property
    def last_inbound_date(self) -> date | None:
        inbound = self.inbound
        return max((m.sent_on for m in inbound), default=None)

    @property
    def outbound_count(self) -> int:
        return sum(1 for m in self.messages if m.direction is Direction.OUTBOUND)


def _d(days_before: int) -> date:
    """A date `days_before` days prior to the demo's as-of date."""
    return AS_OF - timedelta(days=days_before)


# ---------------------------------------------------------------------------
# Showcase threads. The demo narrates these three, so they're hand-written
# rather than generated — the exact wording is what the agent is shown finding.
# ---------------------------------------------------------------------------

# INV-1023 — ABC Logistics. Case A: a credible promise from a long-standing
# customer with no dispute history. The correct outcome is a gentle reminder,
# not escalation, even though the invoice is 17 days overdue.
THREAD_INV_1023 = CommunicationThread(
    invoice_id="INV-1023",
    customer_id="CUST-001",
    messages=[
        Message(
            _d(20), Channel.EMAIL, Direction.OUTBOUND,
            "Dear Sir, Please find attached invoice INV-1023 dated 01/07 for Rs 4,80,000 "
            "against the July consignment. Kindly arrange payment as per agreed terms. "
            "Regards, Accounts",
        ),
        Message(
            _d(18), Channel.EMAIL, Direction.INBOUND,
            "Received, thank you. Forwarding to our accounts team for processing. "
            "Should be in the next payment run.",
        ),
        Message(
            _d(9), Channel.WHATSAPP, Direction.OUTBOUND,
            "Good morning sir, gentle reminder on INV-1023 (4.8L), due date was 31/07. "
            "Please let us know the status.",
        ),
        Message(
            _d(8), Channel.WHATSAPP, Direction.INBOUND,
            "Yes ji, sorry for delay. Our payment run got pushed because of the audit. "
            "We will clear this by Friday, payment is in process. You have my word.",
        ),
        Message(
            _d(3), Channel.WHATSAPP, Direction.OUTBOUND,
            "Thank you sir. Just confirming — Friday 21st?",
        ),
        Message(
            _d(3), Channel.WHATSAPP, Direction.INBOUND,
            "Correct, 21st. Will share UTR once done.",
        ),
    ],
)

# INV-1038 — Global Retail. Case B: the financing candidate. Not yet due, no
# problem in the relationship. There is nothing here to chase — the invoice is
# simply a source of cash the business could pull forward.
THREAD_INV_1038 = CommunicationThread(
    invoice_id="INV-1038",
    customer_id="CUST-002",
    messages=[
        Message(
            _d(26), Channel.EMAIL, Direction.OUTBOUND,
            "Dear Team, Please find invoice INV-1038 for Rs 3,20,000 attached, "
            "against PO 44821. Payment terms 30 days. Regards, Accounts",
        ),
        Message(
            _d(24), Channel.EMAIL, Direction.INBOUND,
            "Acknowledged. Invoice has been entered and approved in our system. "
            "It will go out as per our standard cycle.",
        ),
        Message(
            _d(11), Channel.EMAIL, Direction.INBOUND,
            "FYI our finance calendar has shifted slightly this quarter. No issue with "
            "the invoice itself — approval is done at our end.",
        ),
    ],
)

# INV-1042 — Apex Trading. Case C: three promises, none kept. This is the case
# that separates a real Investigator from keyword matching. The literal text
# contains a payment promise; the pattern says it is worthless.
THREAD_INV_1042 = CommunicationThread(
    invoice_id="INV-1042",
    customer_id="CUST-004",
    messages=[
        Message(
            _d(80), Channel.EMAIL, Direction.OUTBOUND,
            "Dear Sir, Invoice INV-1042 for Rs 2,10,000 attached, due 25/06. "
            "Kindly process. Regards, Accounts",
        ),
        Message(
            _d(74), Channel.EMAIL, Direction.INBOUND,
            "Noted. Will process next week.",
        ),
        Message(
            _d(60), Channel.WHATSAPP, Direction.OUTBOUND,
            "Sir, INV-1042 is now past due. Kindly update.",
        ),
        Message(
            _d(58), Channel.WHATSAPP, Direction.INBOUND,
            "Ha ji, we are arranging. Definitely by month end.",
        ),
        Message(
            _d(45), Channel.WHATSAPP, Direction.OUTBOUND,
            "Sir, month end has passed. INV-1042 still pending, 2.1L. "
            "Please share payment date.",
        ),
        Message(
            _d(43), Channel.WHATSAPP, Direction.INBOUND,
            "Some collection issues at our end. Give us 10 days, we will settle fully.",
        ),
        Message(
            _d(28), Channel.EMAIL, Direction.OUTBOUND,
            "Dear Sir, This is our third follow-up on INV-1042 (Rs 2,10,000), now over "
            "45 days past due. We would like to avoid escalation. Kindly revert with a "
            "firm payment date. Regards, Accounts",
        ),
        Message(
            _d(21), Channel.WHATSAPP, Direction.OUTBOUND,
            "Sir, awaiting your response. Please call back.",
        ),
        Message(
            _d(14), Channel.WHATSAPP, Direction.OUTBOUND,
            "Sir, still no response on INV-1042. Kindly revert.",
        ),
    ],
)

# INV-1051 — Sunrise Textiles. A genuine quality dispute. This must suppress
# both escalation and financing until a human resolves it: escalating a disputed
# invoice damages the relationship and weakens any later statutory claim.
THREAD_INV_1051 = CommunicationThread(
    invoice_id="INV-1051",
    customer_id="CUST-007",
    messages=[
        Message(
            _d(30), Channel.EMAIL, Direction.OUTBOUND,
            "Dear Sir, Invoice INV-1051 for Rs 1,75,000 attached against the August "
            "supply. Regards, Accounts",
        ),
        Message(
            _d(26), Channel.EMAIL, Direction.INBOUND,
            "We have an issue with this consignment. Roughly 15% of the lot did not "
            "match the approved sample — shade variation. Our QC has photographs. "
            "We cannot process the full invoice value until this is sorted out.",
        ),
        Message(
            _d(24), Channel.EMAIL, Direction.OUTBOUND,
            "Sir, we have received your QC note and are reviewing internally. "
            "Could you share the photographs and the lot numbers affected?",
        ),
        Message(
            _d(22), Channel.EMAIL, Direction.INBOUND,
            "Attaching photographs. Lots SR-4471 and SR-4472. We are open to a partial "
            "settlement or a replacement supply, whichever you prefer. But full payment "
            "is not possible as things stand.",
        ),
    ],
)

# INV-1047 — Nova Components. Routine, healthy, recently overdue. Included so
# the agent has an unremarkable case to return an unremarkable finding on.
THREAD_INV_1047 = CommunicationThread(
    invoice_id="INV-1047",
    customer_id="CUST-005",
    messages=[
        Message(
            _d(35), Channel.EMAIL, Direction.OUTBOUND,
            "Dear Team, Invoice INV-1047 for Rs 96,000 attached. Regards, Accounts",
        ),
        Message(
            _d(33), Channel.EMAIL, Direction.INBOUND,
            "Received with thanks.",
        ),
        Message(
            _d(2), Channel.WHATSAPP, Direction.OUTBOUND,
            "Hi, small reminder on INV-1047 (96K), crossed due date this week.",
        ),
    ],
)

SHOWCASE_THREADS: list[CommunicationThread] = [
    THREAD_INV_1023,
    THREAD_INV_1038,
    THREAD_INV_1042,
    THREAD_INV_1051,
    THREAD_INV_1047,
]


# ---------------------------------------------------------------------------
# Generated filler for the rest of the portfolio. Deliberately plainer than the
# showcase threads — most real correspondence is unremarkable, and an agent that
# only ever sees dramatic cases isn't being tested on anything.
# ---------------------------------------------------------------------------

# Customers who reply at all. Apex (CUST-004) has gone quiet by design.
_RESPONSIVE = {"CUST-001", "CUST-002", "CUST-003", "CUST-005", "CUST-006", "CUST-008"}

_ACK_REPLIES = [
    "Received, thank you.",
    "Noted, forwarding to accounts.",
    "Acknowledged. Will process in the usual cycle.",
    "Thanks, entered in our system.",
]

_CHASE_REPLIES = [
    "Checking with our accounts team, will revert.",
    "Should go out in this week's run.",
    "Sorry for the delay, it is in process.",
    "Will update you by tomorrow.",
]


def build_threads(invoices, *, seed: int = 727) -> dict[str, CommunicationThread]:
    """Build the full thread set, keyed by invoice id.

    Showcase threads are used verbatim where they exist; everything else gets a
    plausible generated thread whose shape depends on how overdue the invoice is
    and whether that customer answers at all.
    """
    import random

    rng = random.Random(seed)
    threads = {t.invoice_id: t for t in SHOWCASE_THREADS}

    for invoice in invoices:
        if invoice.invoice_id in threads:
            continue

        days_overdue = (AS_OF - invoice.due_date).days
        messages = [
            Message(
                _d(max(days_overdue + 28, 1)),
                Channel.EMAIL,
                Direction.OUTBOUND,
                f"Dear Sir, Please find invoice {invoice.invoice_id} for "
                f"Rs {int(invoice.invoice_amount):,} attached. Regards, Accounts",
            )
        ]

        responsive = invoice.customer_id in _RESPONSIVE
        if responsive:
            messages.append(
                Message(
                    _d(max(days_overdue + 25, 1)),
                    Channel.EMAIL,
                    Direction.INBOUND,
                    rng.choice(_ACK_REPLIES),
                )
            )

        # Chase cadence rises with how late it is.
        for n, gap in enumerate((14, 7, 3)):
            if days_overdue <= gap:
                continue
            messages.append(
                Message(
                    _d(gap),
                    Channel.WHATSAPP,
                    Direction.OUTBOUND,
                    f"Reminder on {invoice.invoice_id}, "
                    f"{days_overdue} days past due. Kindly update.",
                )
            )
            # Responsive customers answer the first couple of chases, then tail off.
            if responsive and n < 2 and rng.random() < 0.7:
                messages.append(
                    Message(
                        _d(max(gap - 1, 0)),
                        Channel.WHATSAPP,
                        Direction.INBOUND,
                        rng.choice(_CHASE_REPLIES),
                    )
                )

        threads[invoice.invoice_id] = CommunicationThread(
            invoice_id=invoice.invoice_id,
            customer_id=invoice.customer_id,
            messages=sorted(messages, key=lambda m: m.sent_on),
        )

    return threads


# Promise history per customer, observed across past invoices rather than the
# thread being scored. This is what lets the Investigator distinguish a credible
# promise from Apex Trading's fourth identical assurance — and, like
# average_delay_days, it's derived from history rather than handed over.
PROMISE_HISTORY: dict[str, dict[str, int]] = {
    "CUST-001": {"promises_made": 6, "promises_kept": 6},
    "CUST-002": {"promises_made": 3, "promises_kept": 3},
    "CUST-003": {"promises_made": 4, "promises_kept": 4},
    "CUST-004": {"promises_made": 3, "promises_kept": 0},
    "CUST-005": {"promises_made": 5, "promises_kept": 4},
    "CUST-006": {"promises_made": 4, "promises_kept": 3},
    "CUST-007": {"promises_made": 3, "promises_kept": 2},
    "CUST-008": {"promises_made": 7, "promises_kept": 7},
}


def promise_reliability(customer_id: str) -> float | None:
    """Share of past promises this customer actually kept. None if never promised."""
    history = PROMISE_HISTORY.get(customer_id)
    if not history or history["promises_made"] == 0:
        return None
    return history["promises_kept"] / history["promises_made"]
