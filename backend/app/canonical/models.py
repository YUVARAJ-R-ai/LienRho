"""Canonical data model (FR-001, PRD §8).

Every connector (Tally, Zoho, ...) normalizes into these shapes regardless
of source system. Nothing downstream — ML, rules engine, agents, decision
engine — should ever read a connector's native format directly.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"


class CanonicalInvoice(BaseModel):
    org_id: str
    invoice_id: str
    customer_id: str
    invoice_amount: Decimal
    invoice_date: date
    due_date: date
    acceptance_date: date | None = None
    payment_status: PaymentStatus
    payment_date: date | None = None


class CanonicalCustomer(BaseModel):
    org_id: str
    customer_id: str
    customer_name: str
    industry: str | None = None
    customer_type: str | None = None
    average_delay_days: float | None = None
    relationship_duration_days: int | None = None
    treds_status: str | None = None


class CanonicalPayment(BaseModel):
    org_id: str
    invoice_id: str
    # Denormalized from the invoice so payment history is usable for ML features
    # (per-customer delay statistics) without joining through invoices, which
    # may have been archived out of the canonical store.
    customer_id: str
    due_date: date
    actual_payment_date: date | None = None
    days_delayed: int | None = None
    payment_amount: Decimal
    payment_status: PaymentStatus


class SupplierProfile(BaseModel):
    """The MSME running LIENRHO — its own registration details.

    Unlike everything else in this module, this does *not* come from a
    connector: Udyam registration is establishment data captured at org
    onboarding, not something Tally or Zoho holds. It lives here anyway because
    it is canonical business data that more than one module needs.

    Required by the escalation dossier (FR-013), which has to state who is
    filing and under what registration — a statutory claim from an unidentified
    supplier is not a claim.
    """

    org_id: str
    legal_name: str
    udyam_registration_number: str
    enterprise_category: str  # Micro | Small | Medium, per the MSMED classification
    address: str
    contact_email: str


class BusinessFinancialState(BaseModel):
    org_id: str
    as_of_date: date
    current_cash: Decimal
    expected_inflows: Decimal
    upcoming_expenses: Decimal
    payroll: Decimal
    supplier_payments: Decimal
    cash_threshold: Decimal
