"""Shared test setup.

The suite runs with the in-memory approval store by default so it needs no
database — CI has no Postgres service for the general suite, and a teammate
should be able to clone and run `pytest` before running `docker compose up`.

`tests/test_approval_store.py` is the exception: it runs the *same* contract
against both stores, skipping the SQL one when no database is reachable.
"""

import pytest

from app.decision_engine.store import InMemoryApprovalStore, set_approval_store


@pytest.fixture(autouse=True)
def _isolated_approval_store():
    """Give every test a clean, process-local store.

    Autouse because approvals are global state: a test that approves an invoice
    would otherwise change what the next test sees in the queue.
    """
    set_approval_store(InMemoryApprovalStore())
    yield
    set_approval_store(None)
