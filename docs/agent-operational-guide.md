# LLM Agents — Operational Guide

> How to run, test, and switch the LLM agents (`LLMInvestigator`, `LLMStrategist`) without a live LLM, and what to change to go live.

---

## 1. What exists

| Agent | File | LLM shape | Fallback |
|-------|------|-----------|----------|
| `LLMInvestigator` | `backend/app/agents/investigator.py` | `LiteLLMChatModel(client, model_tier="cheap")` → `.with_structured_output(InvestigatorFindings)` (standard `json_schema`) | `RuleBasedInvestigator` |
| `LLMStrategist` | `backend/app/agents/strategy.py` | LangGraph `create_agent` ReAct loop, tools = `build_toolbox_tools(box)`, model tier `frontier` | `RuleBasedStrategist` |

Both are behind the same interface as their rule-based counterparts and validate against the same Pydantic schemas (ADR-002). The decision engine cannot tell them apart.

**The LLM never computes statutory/financial/interest values** (CON-05, ADR-002, NFR-003). The strategist only learns those numbers by calling `ToolBox` tools; `_facts_missing` grounds the recommendation, and `StrategyResult.fallback_reason` records why any run fell back.

---

## 2. Test without any LLM or key (mock mode)

The whole agent layer runs against `MockLLMClient` (`backend/app/agents/llm_client.py`), a scripted fake that pops the next canned response per call and replays the last one. No network, no provider, no key.

```powershell
cd backend
uv run pytest -q                      # full suite (175 tests)
uv run pytest tests/test_llm_investigator.py -q
uv run pytest tests/test_llm_strategist.py -q
uv run ruff check app tests           # lint
```

What the LLM tests verify:

| Test file | Behavior verified |
|-----------|-------------------|
| `test_llm_investigator.py` | Validated findings; ADR-004 history overwrite (model cannot invent reliability); cheap tier + standard `json_schema` response format; fallbacks (malformed output, gateway failure, invalid schema); swappable fallback |
| `test_llm_strategist.py` | `create_agent` tool loop with recorded `ToolBox` calls; FINANCE requires the TReDS tool; fallbacks (ungrounded escalate, gateway failure, malformed answer, runaway loop past `_max_steps` → `recursion_limit`); unknown tool reported back to the model as an error; frontier tier; interest only computed when requested |

Run one test verbosely to watch a simulated tool loop:

```powershell
uv run pytest tests/test_llm_strategist.py::test_llm_strategist_executes_tool_loop_and_grounds_the_recommendation -q -s
```

### 2.1 How the mock works

A scripted two- or three-turn tool loop is written as a list of dicts:

```python
client = MockLLMClient([
    {"tool_calls": [{"name": "check_msmed_threshold", "arguments": {...}}]},  # turn 1: ask for a fact
    {"tool_calls": [{"name": "calculate_interest", "arguments": {...}}]},     # turn 2: ask for another
    {"content": '{"action": "ESCALATE", "reason": "...", "deciding_factors": [...], "confidence": 0.85}'},  # turn 3: final answer
])
```

Each `chat()` call pops the next entry; when exhausted, the last one replays — so an out-of-control tool loop is simulated by a script that keeps returning `tool_calls`.

---

## 3. Switching the agents on (real gateway)

The LLM implementations already exist; enabling them is configuration only.

1. **Set the gateway targeting** in the environment or `backend/app/config.py`:
   - `LLM_GATEWAY_URL` — LiteLLM proxy (or provider) base URL
   - `LLM_API_KEY` — key for the gateway
   - `LLM_CHEAP_MODEL` / `LLM_FRONTIER_MODEL` — model names per tier (investigator → cheap, strategist → frontier)
   - `LLM_REQUEST_TIMEOUT_S` — per-call timeout
2. **Flip `llm_enabled` to `True`.** `get_investigator()` / `get_strategist()` then return the LLM versions instead of the rule-based ones. Default is `False` so the app is fully functional with no key.
3. **Restart** and re-run the API.

No code changes. The factories are the single switch point (`investigator.py`, `strategy.py`).

### 3.1 What happens on failure

Every failure degrades, never fails: gateway timeout/rate-limit/exception, malformed output, schema violation, or a runaway tool loop (`GraphRecursionError`) → the run falls back to the rule-based implementation, and `StrategyResult.fallback_reason` (strategist) or the log line (investigator) says why. Fallback rate is the operational health signal (target < 5%).

---

## 4. Observability (Langfuse)

Traces are captured two ways, both opt-in and guarded so they can never take an agent down:

- **litellm callbacks** — `ensure_langfuse_wiring()` registers `litellm.success_callback = ["langfuse"]` when configured.
- **Graph callbacks** — `get_langfuse_handler()` returns a langfuse `CallbackHandler` attached to the strategist's graph config.

Enable locally:

| Env var | Purpose |
|---------|---------|
| `LANGFUSE_PUBLIC_KEY` | required |
| `LANGFUSE_SECRET_KEY` | required |
| `LANGFUSE_HOST` | deployment URL |
| `LANGFUSE_MOCK=true` | local tracing with no keys (dev only) |

Without any of these, both helpers return silently and the agents run with zero tracing wiring. Token usage is captured on every completion (`LLMResult.usage` → `usage_metadata`) whether or not Langfuse is on.

---

## 5. Common problems

| Symptom | Cause / fix |
|---------|-------------|
| Tests fail with a langfuse auth warning | Stale `LANGFUSE_*` env vars; unset them, or the handlers were built without keys — the guard returns `None` when unset |
| Agent returns the rule-based result despite `llm_enabled=True` | The LLM call failed and the fallback ran — check `StrategyResult.fallback_reason` and the logs |
| Strategist loops forever against a real model | The tool schema/args mismatch `ToolBox` methods; the model should recover from error `ToolMessage`s, and `recursion_limit` (from `_max_steps`) still bounds it |
| `uv run pip list` shows old package versions | Trust `uv run python -c "import importlib.metadata; print(importlib.metadata.version('langgraph'))"` instead; the pinned versions live in `uv.lock` |

---

## 6. Going live checklist

1. ✅ Agents implemented and tested against the mock (175 tests, ruff clean).
2. [ ] Provider/gateway chosen (OQ-02) — set gateway URL, key, model names.
3. [ ] `llm_enabled=True`, restart, smoke-test `/action-queue` and `/invoice/{id}`.
4. [ ] Langfuse keys set; confirm traces appear in the Langfuse UI.
5. [ ] Measure fallback rate on real traffic (< 5% target).
6. [ ] Load test NFR-004: p95 ≤ 3.0s @ 100 invoices with LLM calls.