"""The scheduled half of FR-001 ("on a scheduled and on-demand basis").

A plain asyncio task rather than APScheduler or Celery. CON-01 fixes the stack,
and a periodic call in a single-process deployment does not need a scheduler
library — adding one would buy persistence and clustering that a modular
monolith with one worker cannot use anyway.

That limit is real and worth stating: with more than one worker process, every
worker runs this loop, so N workers means N syncs per interval. Syncs are
idempotent (FR-001 AC-3) so the result is correct rather than corrupted, but it
is wasted reads against someone's accounting system. A deployment that scales
out should set `sync_interval_minutes=0` and drive `POST /api/sync` from
whatever already schedules its jobs.

Disabled by default. A dev machine should not quietly poll a Tally instance
every few minutes because someone left the setting on.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

logger = logging.getLogger(__name__)


def scheduled_org_ids() -> list[str]:
    """Orgs the background sync covers.

    It runs outside any request, so there is no access token to name the tenant
    and it has to be configured. Deliberately not "every org in the table":
    syncing a tenant nobody asked for means holding credentials for it and
    hitting their accounting system on our own initiative.
    """
    from app.config import settings

    return [org.strip() for org in settings.sync_org_ids.split(",") if org.strip()]


async def _sync_once() -> None:
    from app.config import settings
    from app.connectors import get_connector
    from app.db.session import SessionLocal

    source = settings.sync_connector
    try:
        connector = get_connector(source)
    except (RuntimeError, ValueError) as exc:
        logger.warning("scheduled sync skipped — connector not configured: %s", exc)
        return

    for org_id in scheduled_org_ids():
        # to_thread because the connector and session are both blocking, and
        # holding the event loop through an HTTP round-trip to Tally would
        # stall every request the API is serving.
        try:
            result = await asyncio.to_thread(_sync_org, SessionLocal, connector, org_id, source)
        except Exception as exc:  # noqa: BLE001 - one org must not stop the rest
            logger.warning("scheduled sync raised for %s: %s", org_id, exc)
            continue

        if result.succeeded:
            logger.info(
                "scheduled sync ok for %s: %d invoices, %d customers, %d payments",
                org_id,
                result.invoices_synced,
                result.customers_synced,
                result.payments_synced,
            )
        else:
            logger.warning("scheduled sync failed for %s: %s", org_id, result.error)


def _sync_org(session_factory, connector, org_id: str, source: str):
    from app.sync.service import sync_portfolio

    with session_factory() as session:
        return sync_portfolio(session, org_id=org_id, connector=connector, source=source)


async def run_scheduled_sync() -> None:
    """Sync every configured org, forever, on the configured interval."""
    from app.config import settings

    interval = settings.sync_interval_minutes * 60
    logger.info(
        "scheduled sync every %d min from %s for %s",
        settings.sync_interval_minutes,
        settings.sync_connector,
        ", ".join(scheduled_org_ids()),
    )

    while True:
        # Sleep first: an API restart should not trigger a sync burst, and
        # during a crash-loop that would be a read storm against Tally.
        await asyncio.sleep(interval)
        with contextlib.suppress(asyncio.CancelledError):
            await _sync_once()


def should_run() -> bool:
    from app.config import settings

    if settings.sync_interval_minutes <= 0:
        return False
    if not scheduled_org_ids():
        logger.warning(
            "sync_interval_minutes is set but sync_org_ids is empty; "
            "the scheduled sync has no tenant to sync and will not start."
        )
        return False
    return True
