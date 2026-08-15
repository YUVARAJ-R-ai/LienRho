"""LangGraph agents: Receivables Investigator, Recovery Strategy, Execution (FR-007, FR-008).

Every agent call returns a Pydantic-validated object (ADR-002). Agents call
rules_engine/ml_core functions as tools — they never compute statutory or
financial values themselves.
"""
