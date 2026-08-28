"""TallyPrime connector (FR-001, CON-02, #6).

TallyPrime exposes an HTTP gateway that accepts XML request envelopes, and this
module speaks that protocol. Built against Tally's published developer
reference for the XML integration format.

**ASM-01 is still open.** The gateway has not been exercised against a live
TallyPrime instance from this codebase — no instance was reachable during
development. Everything here is verified against recorded fixtures of the
documented format, which means the envelope construction, the status handling,
and the canonical mapping are all tested, but the assumption that a real Tally
answers exactly this way is not yet evidence. Treat the first run against a
real instance as the spike ASM-01 asks for, and expect tag-name surprises:
`parser.py` is deliberately tolerant about which of several documented spellings
a field arrives under, for that reason.
"""

from app.connectors.tally.connector import TallyConfig, TallyConnector
from app.connectors.tally.transport import HttpTallyTransport, TallyTransport

__all__ = ["HttpTallyTransport", "TallyConfig", "TallyConnector", "TallyTransport"]
