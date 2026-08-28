"""Getting XML to and from the Tally gateway (#6).

The transport is a separate seam from the connector so the connector's mapping
logic can be tested without a TallyPrime instance — which matters here, because
ASM-01 means there is no instance to test against yet. A fake transport
replaying a recorded envelope exercises every line of parsing and canonical
mapping; only the socket is stubbed.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from app.connectors.errors import ConnectorUnavailable


class TallyTransport(ABC):
    """Sends one XML envelope and returns the raw XML response."""

    @abstractmethod
    def send(self, xml: str) -> str: ...


class HttpTallyTransport(TallyTransport):
    """Talks to the TallyPrime HTTP gateway (POST XML to port 9000 by default).

    Uses urllib rather than adding an HTTP client dependency: the protocol is
    one POST with an XML body, which needs nothing a library would provide.
    """

    def __init__(self, url: str = "http://localhost:9000", *, timeout_s: float = 30.0) -> None:
        self.url = url
        self.timeout_s = timeout_s

    def send(self, xml: str) -> str:
        request = urllib.request.Request(
            self.url,
            data=xml.encode("utf-8"),
            # Tally's gateway is content-type agnostic in practice, but sending
            # the correct one costs nothing and helps anything in between.
            headers={"Content-Type": "text/xml; charset=utf-8"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                raw = response.read()
        except urllib.error.URLError as exc:
            # Connection refused is the overwhelmingly common case: Tally is
            # running but its gateway is switched off, which is a settings
            # change in Tally rather than anything this side can fix.
            raise ConnectorUnavailable(
                f"Could not reach the TallyPrime gateway at {self.url}: {exc.reason}. "
                "Check that Tally is running and its HTTP gateway is enabled."
            ) from exc
        except TimeoutError as exc:
            raise ConnectorUnavailable(
                f"TallyPrime at {self.url} did not respond within {self.timeout_s}s."
            ) from exc

        # Tally emits ISO-8859-1 by default and does not always declare it.
        # Decoding as UTF-8 strictly would fail on a rupee sign or an accented
        # customer name, so decode leniently rather than lose the response.
        return raw.decode("utf-8", errors="replace")


class RecordedTallyTransport(TallyTransport):
    """Replays canned responses in order. For tests and for offline development.

    Keeps the request envelopes it was given, so a test can assert what was
    asked for as well as what came back.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.sent: list[str] = []

    def send(self, xml: str) -> str:
        self.sent.append(xml)
        if not self._responses:
            raise AssertionError("RecordedTallyTransport ran out of responses")
        return self._responses.pop(0)
