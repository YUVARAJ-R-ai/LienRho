"""org-composite primary keys, and payments no longer FK to invoices

Two defects that only became reachable once the sync path started writing to
these tables (FR-001).

1. `customers.customer_id` and `invoices.invoice_id` were primary keys on their
   own. Invoice and customer numbers are unique *within* an accounting system,
   not globally, so two tenants running the same software collide — the second
   org's sync failed on a duplicate key instead of being isolated from the
   first. The org is now part of the key (NFR-001, BR-TENANT).

2. `payments.invoice_id` referenced `invoices.invoice_id`. Payment history is
   the delay model's training signal and reaches further back than the open
   invoice set; `CanonicalPayment` already documented that the invoice "may have
   been archived out of the canonical store". The constraint made it impossible
   to load history for a closed invoice, which is most of the history worth
   having.

Revision ID: 6ab21c9d4e77
Revises: 59f7d3b1fe2b
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6ab21c9d4e77"
down_revision: str | Sequence[str] | None = "59f7d3b1fe2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop dependents before the keys they point at.
    op.drop_constraint("payments_invoice_id_fkey", "payments", type_="foreignkey")
    op.drop_constraint("payments_customer_id_fkey", "payments", type_="foreignkey")
    op.drop_constraint("invoices_customer_id_fkey", "invoices", type_="foreignkey")

    op.drop_constraint("invoices_pkey", "invoices", type_="primary")
    op.drop_constraint("customers_pkey", "customers", type_="primary")

    op.create_primary_key("customers_pkey", "customers", ["org_id", "customer_id"])
    op.create_primary_key("invoices_pkey", "invoices", ["org_id", "invoice_id"])

    op.create_foreign_key(
        "invoices_customer_fkey",
        "invoices",
        "customers",
        ["org_id", "customer_id"],
        ["org_id", "customer_id"],
    )
    op.create_foreign_key(
        "payments_customer_fkey",
        "payments",
        "customers",
        ["org_id", "customer_id"],
        ["org_id", "customer_id"],
    )
    # Deliberately no payments -> invoices foreign key; see the module docstring.


def downgrade() -> None:
    op.drop_constraint("payments_customer_fkey", "payments", type_="foreignkey")
    op.drop_constraint("invoices_customer_fkey", "invoices", type_="foreignkey")

    op.drop_constraint("invoices_pkey", "invoices", type_="primary")
    op.drop_constraint("customers_pkey", "customers", type_="primary")

    op.create_primary_key("customers_pkey", "customers", ["customer_id"])
    op.create_primary_key("invoices_pkey", "invoices", ["invoice_id"])

    op.create_foreign_key(
        "invoices_customer_id_fkey", "invoices", "customers", ["customer_id"], ["customer_id"]
    )
    op.create_foreign_key(
        "payments_customer_id_fkey", "payments", "customers", ["customer_id"], ["customer_id"]
    )
    op.create_foreign_key(
        "payments_invoice_id_fkey", "payments", "invoices", ["invoice_id"], ["invoice_id"]
    )
