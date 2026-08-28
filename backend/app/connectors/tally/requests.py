"""Building Tally XML request envelopes (#6).

Tally's export format is `ENVELOPE > HEADER + BODY`, where HEADER names the
request kind and BODY carries the company and date range, plus an optional TDL
block defining exactly which collection to return and which fields to fetch.

Defining the collection in the request rather than relying on a stock report is
deliberate: a stock report's columns follow the user's Tally configuration, so
two customers running the same Tally version can return different shapes. A
request-defined collection returns what we asked for.
"""

from __future__ import annotations

from datetime import date
from xml.sax.saxutils import escape

# Tally dates are YYYYMMDD with no separators, everywhere, in both directions.
TALLY_DATE_FORMAT = "%Y%m%d"


def format_tally_date(value: date) -> str:
    return value.strftime(TALLY_DATE_FORMAT)


def _static_variables(company: str, from_date: date | None, to_date: date | None) -> str:
    parts = [f"<SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY>"]
    if from_date is not None:
        parts.append(f"<SVFROMDATE>{format_tally_date(from_date)}</SVFROMDATE>")
    if to_date is not None:
        parts.append(f"<SVTODATE>{format_tally_date(to_date)}</SVTODATE>")
    parts.append("<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>")
    return "".join(parts)


def collection_request(
    *,
    company: str,
    collection_name: str,
    collection_type: str,
    fetch: list[str],
    from_date: date | None = None,
    to_date: date | None = None,
    filters: str = "",
) -> str:
    """An Export/Collection envelope for one request-defined TDL collection.

    `fetch` names the fields to return. Asking for exactly what is needed keeps
    the response small — a Tally book with years of history can otherwise return
    tens of megabytes for a request that wanted four columns.
    """
    fetch_lines = "".join(f"<FETCH>{escape(field)}</FETCH>" for field in fetch)
    safe_name = escape(collection_name)

    return (
        "<ENVELOPE>"
        "<HEADER>"
        "<VERSION>1</VERSION>"
        "<TALLYREQUEST>Export</TALLYREQUEST>"
        "<TYPE>Collection</TYPE>"
        f"<ID>{safe_name}</ID>"
        "</HEADER>"
        "<BODY>"
        "<DESC>"
        f"<STATICVARIABLES>{_static_variables(company, from_date, to_date)}</STATICVARIABLES>"
        "<TDL><TDLMESSAGE>"
        f'<COLLECTION NAME="{safe_name}" ISMODIFY="No">'
        f"<TYPE>{escape(collection_type)}</TYPE>"
        f"{fetch_lines}"
        f"{filters}"
        "</COLLECTION>"
        "</TDLMESSAGE></TDL>"
        "</DESC>"
        "</BODY>"
        "</ENVELOPE>"
    )


def customers_request(company: str) -> str:
    """Sundry Debtors ledgers — the customers who owe money.

    Filtered to that group rather than fetching every ledger: a Tally company
    holds bank accounts, tax ledgers, and expense heads in the same table, and
    none of them are customers.
    """
    return collection_request(
        company=company,
        collection_name="LIENRHOCustomers",
        collection_type="Ledger",
        fetch=[
            "Name",
            "Parent",
            "LedgerMobile",
            "Email",
            "OpeningBalance",
            "ClosingBalance",
            "BillCreditPeriod",
        ],
        filters=(
            "<FILTERS>IsCustomer</FILTERS>"
            "<SYSTEM TYPE=\"Formula\" NAME=\"IsCustomer\">"
            "$$IsSundryDebtor:$Parent"
            "</SYSTEM>"
        ),
    )


def invoices_request(company: str, *, from_date: date, to_date: date) -> str:
    """Outstanding receivable bills — one per invoice, with its due date.

    Bills rather than sales vouchers: a bill is what carries the credit period
    and the still-outstanding amount, which is what the whole product reasons
    about. A sales voucher would give the invoice but not what remains unpaid.
    """
    return collection_request(
        company=company,
        collection_name="LIENRHOBills",
        collection_type="Bills",
        fetch=[
            "Name",
            "Parent",
            "BillDate",
            "BillCreditPeriod",
            "ClosingBalance",
            "OpeningBalance",
            "IsAdvance",
        ],
        from_date=from_date,
        to_date=to_date,
    )


def payments_request(company: str, *, from_date: date, to_date: date) -> str:
    """Receipt vouchers — money that actually arrived, and when."""
    return collection_request(
        company=company,
        collection_name="LIENRHOReceipts",
        collection_type="Voucher",
        fetch=[
            "Date",
            "VoucherTypeName",
            "VoucherNumber",
            "PartyLedgerName",
            "Amount",
            "AllLedgerEntries",
            "BillAllocations",
        ],
        from_date=from_date,
        to_date=to_date,
        filters=(
            "<FILTERS>IsReceipt</FILTERS>"
            "<SYSTEM TYPE=\"Formula\" NAME=\"IsReceipt\">"
            "$VoucherTypeName = \"Receipt\""
            "</SYSTEM>"
        ),
    )


def expenses_request(company: str, *, from_date: date, to_date: date) -> str:
    """Expense ledgers, for the outflow half of the cash forecast (FR-004)."""
    return collection_request(
        company=company,
        collection_name="LIENRHOExpenses",
        collection_type="Ledger",
        fetch=["Name", "Parent", "ClosingBalance"],
        from_date=from_date,
        to_date=to_date,
        filters=(
            "<FILTERS>IsExpense</FILTERS>"
            "<SYSTEM TYPE=\"Formula\" NAME=\"IsExpense\">"
            "$$IsExpense:$Parent"
            "</SYSTEM>"
        ),
    )
