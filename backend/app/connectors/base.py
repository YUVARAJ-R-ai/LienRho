"""Connector interface (PRD §24, NFR-006).

A new connector must implement this interface and nothing else outside its
own module. The ML, rules, agent, and decision-engine layers only ever see
the canonical types below — never a connector's native response format.
"""

from abc import ABC, abstractmethod

from app.canonical.models import CanonicalCustomer, CanonicalInvoice, CanonicalPayment


class AccountingConnector(ABC):
    """One implementation per accounting/ERP system (Tally, Zoho, ...)."""

    @abstractmethod
    def get_invoices(self, org_id: str) -> list[CanonicalInvoice]: ...

    @abstractmethod
    def get_customers(self, org_id: str) -> list[CanonicalCustomer]: ...

    @abstractmethod
    def get_payments(self, org_id: str) -> list[CanonicalPayment]: ...

    @abstractmethod
    def get_expenses(self, org_id: str) -> list[dict]: ...

    @abstractmethod
    def create_task(self, org_id: str, description: str) -> None: ...
