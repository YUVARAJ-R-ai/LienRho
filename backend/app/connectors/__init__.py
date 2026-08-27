"""Connector registry (FR-001, NFR-006).

The one place that knows which connectors exist. `get_connector()` is the
"registration point" NFR-006 allows a new connector to touch — everything
downstream takes an `AccountingConnector` and never asks which one it has.
"""

from app.connectors.base import AccountingConnector


def get_connector(source: str) -> AccountingConnector:
    """Build the connector named by `source`.

    Imports inside the branch so a missing or misconfigured connector cannot
    break the other one at import time — a broken Tally config should not stop
    the synthetic demo from starting.
    """
    if source == "tally":
        from app.config import settings
        from app.connectors.tally import TallyConfig, TallyConnector

        if not settings.tally_company:
            raise RuntimeError(
                "source=tally requires tally_company — Tally selects a company by "
                "its display name, and an empty one returns an empty book rather "
                "than an error."
            )
        return TallyConnector(
            TallyConfig(
                company=settings.tally_company,
                url=settings.tally_url,
                history_days=settings.tally_history_days,
            )
        )

    if source == "synthetic":
        from app.connectors.synthetic import SyntheticConnector

        return SyntheticConnector()

    raise ValueError(f"Unknown connector source: {source!r}")


__all__ = ["AccountingConnector", "get_connector"]
