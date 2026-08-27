"""Failures a connector can raise (FR-001, NFR-006).

Named exceptions rather than bare ones so the decision engine can tell "the
accounting system is unreachable" from "the accounting system answered and said
no" — the first is retryable, the second is a configuration problem, and a
generic error would make them look identical.
"""


class ConnectorError(Exception):
    """Base for every connector failure."""


class ConnectorUnavailable(ConnectorError):
    """The accounting system could not be reached at all."""


class ConnectorRejected(ConnectorError):
    """The accounting system was reached and refused the request."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class ConnectorUnsupported(ConnectorError):
    """The source system has no equivalent of the requested operation.

    Distinct from "not implemented yet": raising this says the capability does
    not exist in the source system, so no amount of further work on this
    connector will produce it.
    """
