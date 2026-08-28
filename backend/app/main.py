import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.routes import router as api_router
from app.auth.router import router as auth_router
from app.config import require_production_secrets
from app.sync.scheduler import run_scheduled_sync, should_run


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Own the background sync task for the life of the process (FR-001).

    Started here rather than at import so it exists only in a running server —
    a test client, an Alembic run, or the OpenAPI dump must not spawn a loop
    that reaches out to someone's accounting system.
    """
    task = asyncio.create_task(run_scheduled_sync()) if should_run() else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            # Awaited so shutdown does not race a sync mid-transaction.
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="LIENRHO API", lifespan=lifespan)

# Fails the process at import rather than at the first login, so a deployment
# still carrying the development signing key never starts serving (NFR-002).
require_production_secrets()

# The Next.js dev server runs on a different origin during development.
# Tighten this to the deployed frontend origin before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(api_router)
