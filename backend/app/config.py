from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app config, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://lienrho:lienrho@localhost:5432/lienrho"
    environment: str = "development"

    # --- Decision durability (FR-014, NFR-007) ------------------------------
    # "postgres" keeps approvals and audit trails across an API restart;
    # "memory" is the no-dependency fallback used by the test suite and by a
    # dev machine with no database.
    #
    # Asking for postgres is a preference, not a demand: if the database is
    # unreachable the process falls back to memory and keeps serving rather
    # than refusing to start. The fallback is logged and reported by /health,
    # so a deployment that has quietly stopped being durable is visible rather
    # than something you find out when you need the trail.
    audit_store: Literal["postgres", "memory"] = "postgres"

    # --- Portfolio source (FR-001, CON-02, #6) ------------------------------
    # "synthetic" is the demo dataset; "tally" reads a live TallyPrime company
    # over its XML gateway. Defaults to synthetic because ASM-01 is still open —
    # the connector is implemented and tested against recorded fixtures, but has
    # never been run against a real instance, so making it the default would
    # stake the whole app on an unverified assumption.
    # Where the action queue reads its portfolio from:
    #   synthetic / tally — read live from that connector on every request
    #   database         — read the canonical store, populated by a sync
    # "database" is the shape FR-001 describes; the live modes stay because the
    # demo should not require a sync to have run first.
    portfolio_source: Literal["synthetic", "tally", "database"] = "synthetic"

    # Which connector a sync pulls *from*. Independent of the above: you sync
    # from Tally into the store and then serve the queue from the store.
    sync_connector: Literal["synthetic", "tally"] = "synthetic"

    # Background sync interval in minutes; 0 disables it. FR-001 asks for
    # scheduled *and* on-demand — POST /api/sync is the on-demand half. Off by
    # default so a dev machine does not quietly hammer a Tally instance.
    sync_interval_minutes: int = 0
    # Orgs the scheduled sync covers. It runs outside a request, so there is no
    # token to name the tenant and it has to be told.
    sync_org_ids: str = ""

    tally_company: str = ""
    tally_url: str = "http://localhost:9000"
    tally_history_days: int = 365

    # --- Auth (NFR-001, NFR-002) --------------------------------------------
    # The signing key for access tokens. The default is a visible dev-only
    # placeholder: `require_production_secrets()` refuses to serve with it when
    # environment != "development", so a deployment cannot inherit it silently.
    jwt_secret: str = "dev-only-insecure-signing-key-not-for-deployment"
    jwt_ttl_minutes: int = 12 * 60

    # --- LLM gateway (OQ-02) ------------------------------------------------
    # The agent layer talks to an OpenAI-compatible endpoint (LiteLLM gateway
    # or a direct provider). Until a gateway + virtual key exist, the factories
    # in agents/investigator.py and agents/strategy.py keep returning the
    # rule-based implementations and no LLM call is ever attempted.
    llm_enabled: bool = False
    llm_gateway_url: str = ""
    llm_api_key: str = ""
    # Model tier -> provider model name. "cheap" handles extraction/classification,
    # "frontier" handles the reasoning loop (production-guide BB1: route by complexity).
    llm_cheap_model: str = ""
    llm_frontier_model: str = ""
    # Hard cap on agent tool-loop steps — a runaway loop is a spend event (agentic-loop 06).
    llm_max_steps: int = 6
    llm_request_timeout_s: float = 30.0


settings = Settings()

DEV_JWT_SECRET = "dev-only-insecure-signing-key-not-for-deployment"


def require_production_secrets() -> None:
    """Fail fast if a non-development environment is using the dev signing key.

    Checked at app startup rather than at first login, so the problem surfaces
    on deploy instead of on the first request that happens to authenticate.
    """
    if settings.environment != "development" and settings.jwt_secret == DEV_JWT_SECRET:
        raise RuntimeError(
            f"jwt_secret is still the development default while environment="
            f"{settings.environment!r}. Set JWT_SECRET before serving (NFR-002)."
        )
