from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.routes import router as api_router
from app.auth.router import router as auth_router
from app.config import require_production_secrets

app = FastAPI(title="LIENRHO API")

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
