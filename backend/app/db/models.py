"""ORM tables for the canonical data model (FR-001). Mirrors app/canonical/models.py.

Every table inherits OrgScopedMixin (NFR-001, BR-TENANT) — query helpers in
app/db/scoping.py are the only sanctioned way to read/write these tables so
no endpoint can forget the org_id filter.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import ForeignKey, String
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
