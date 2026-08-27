"""ORM tables for the canonical data model (FR-001). Mirrors app/canonical/models.py.

Every table inherits OrgScopedMixin (NFR-001, BR-TENANT) — query helpers in
app/db/scoping.py are the only sanctioned way to read/write these tables so
no endpoint can forget the org_id filter.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OrgScopedMixin:
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)


class Invoice(OrgScopedMixin, Base):
    __tablename__ = "invoices"

    invoice_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"))
    invoice_amount: Mapped[Decimal]
    invoice_date: Mapped[date]
    due_date: Mapped[date]
    acceptance_date: Mapped[date | None]
    payment_status: Mapped[str]
    payment_date: Mapped[date | None]


class Customer(OrgScopedMixin, Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_name: Mapped[str]
    industry: Mapped[str | None]
    customer_type: Mapped[str | None]
    average_delay_days: Mapped[float | None]
    relationship_duration_days: Mapped[int | None]
    treds_status: Mapped[str | None]


class Payment(OrgScopedMixin, Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.invoice_id"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    due_date: Mapped[date]
    actual_payment_date: Mapped[date | None]
    days_delayed: Mapped[int | None]
    payment_amount: Mapped[Decimal]
    payment_status: Mapped[str]


class BusinessFinancialState(OrgScopedMixin, Base):
    __tablename__ = "business_financial_state"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    as_of_date: Mapped[date]
    current_cash: Mapped[Decimal]
    expected_inflows: Mapped[Decimal]
    upcoming_expenses: Mapped[Decimal]
    payroll: Mapped[Decimal]
    supplier_payments: Mapped[Decimal]
    cash_threshold: Mapped[Decimal]


class ActionDecision(OrgScopedMixin, Base):
    """The current human decision on one invoice's recommendation (FR-010, FR-014).

    One row per (org, invoice): the *state*, not the history. The sequence of
    decisions that produced it lives in `audit_log_entries`, because an
    approve-then-reject is two facts about who decided what and FR-014 asks for
    both. Storing only the latest state here keeps the replay in one place.
    """

    __tablename__ = "action_decisions"

    org_id: Mapped[str] = mapped_column(String, primary_key=True)
    invoice_id: Mapped[str] = mapped_column(String, primary_key=True)
    approval_state: Mapped[str]
    # Nullable: a decision can be recorded before the action is known, and a
    # sentinel string here would fail to parse back into RecommendedAction.
    recommended_action: Mapped[str | None]
    decided_by: Mapped[str]
    decided_at: Mapped[datetime]


class AuditLogEntry(OrgScopedMixin, Base):
    """One durable line of the FR-014 audit trail: what, why, who, when.

    `sequence` orders entries within an invoice. It is stored explicitly rather
    than relying on the timestamp because several entries are written inside the
    same call and would otherwise share a timestamp to the microsecond, leaving
    an approve-then-reject pair with no defined order — which is exactly the
    ordering NFR-007 needs to hold.
    """

    __tablename__ = "audit_log_entries"
    # Matches how the trail is read — one invoice, in order — and makes a
    # duplicated sequence number impossible if a rewrite ever races.
    __table_args__ = (
        UniqueConstraint("org_id", "invoice_id", "sequence", name="uq_audit_entry_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(String, index=True)
    sequence: Mapped[int]
    timestamp: Mapped[str]
    decided_by: Mapped[str]  # ML | RULES | TOOL | AGENT | HUMAN
    what: Mapped[str] = mapped_column(Text)
    why: Mapped[str] = mapped_column(Text)


class Org(OrgScopedMixin, Base):
    """A tenant. The root of every org_id in this schema (NFR-001, BR-TENANT).

    `org_id` is the primary key rather than a surrogate: it is what every other
    table already carries and what the access token asserts, so a second
    identifier would only create a mapping that could disagree with itself.
    """

    __tablename__ = "orgs"

    org_id: Mapped[str] = mapped_column(String, primary_key=True)
    org_name: Mapped[str]
    created_at: Mapped[datetime]


class User(OrgScopedMixin, Base):
    """A person who signs in, belonging to exactly one org.

    Email is globally unique, not unique per org. Two orgs sharing one login
    would make the token's `org` claim ambiguous, and the whole point of the
    claim is that it is not.
    """

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str]
    display_name: Mapped[str]
    created_at: Mapped[datetime]
