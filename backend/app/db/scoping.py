"""Org-scoped query helper (NFR-001, BR-TENANT).

Endpoints must read/write through `org_scoped`, not raw `session.query`, so
tenant isolation isn't something every endpoint author has to remember.

Auth isn't built yet (see ASM-04/OQ-02) — get_current_org_id is a stub that
trusts an X-Org-Id header. Replace with real auth before anything but local
dev touches this.
"""

from fastapi import Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OrgScopedMixin


def get_current_org_id(x_org_id: str = Header(...)) -> str:
    return x_org_id


def org_scoped(db: Session, model: type[OrgScopedMixin], org_id: str):
    """Return a SELECT for `model` pre-filtered to `org_id`."""
    return db.execute(select(model).where(model.org_id == org_id)).scalars()
