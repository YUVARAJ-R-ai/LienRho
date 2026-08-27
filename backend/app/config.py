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
    # dev machine with no database. Chosen explicitly rather than by probing
    # the database, because an audit trail that quietly stops being durable is
    # worse than one that fails loudly — nothing downstream can tell the
    # difference until the trail is needed.
    audit_store: Literal["postgres", "memory"] = "postgres"

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
