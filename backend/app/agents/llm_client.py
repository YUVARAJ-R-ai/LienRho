"""The LLM seam contract (OQ-02, issue #13).

This module is the *only* thing the agent layer knows about the outside LLM
world. Teammates building the LiteLLM gateway, per-org virtual keys, model
routing, or budgets implement this interface — the agents never touch a
provider SDK directly.

Two rules make the seam safe to build against before the gateway exists:

1. **OpenAI-compatible wire format.** `chat()` accepts OpenAI-style messages
   and tool schemas, so the real gateway (LiteLLM proxy, any provider, a
   local Ollama) drops in without the agents changing. `TOOL_SCHEMAS` in
   agents/tools.py already is that format.
2. **A mock exists for tests.** `MockLLMClient` is scripted, so the entire
   agent layer (Investigator single call, Strategist tool loop, fallbacks)
   is verified with no network, no key, and zero cost. The gateway is a
   configuration detail after this.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, convert_to_openai_messages
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

logger = logging.getLogger(__name__)

# Model tiers the agent layer may ask for. The gateway maps these to concrete
# provider models; agents should not name providers (BB1: route by complexity).
CHEAP_TIER = "cheap"
FRONTIER_TIER = "frontier"

# Message shapes, for the type-checker's sake. `chat()` accepts dicts in the
# OpenAI chat-completions format:
#   {"role": "system"|"user"|"assistant"|"tool", "content": str, ...}
ChatMessage = dict[str, Any]


def ensure_langfuse_wiring() -> None:
    """Register litellm's native langfuse logger, guarded so it can never break.

    litellm 1.97 ships a first-party `langfuse` callback (LangFuseLogger). We
    opt in only when a Langfuse deployment is actually configured — missing keys
    in a local dev box should degrade to "no traces", never to "no LLM calls".
    """
    import os

    if not (os.getenv("LANGFUSE_PUBLIC_KEY") or os.getenv("LANGFUSE_MOCK")):
        return
    try:
        import litellm

        if "langfuse" not in litellm.success_callback:
            litellm.success_callback = ["langfuse"]
            litellm.failure_callback = ["langfuse"]
        logger.info("litellm -> langfuse tracing enabled")
    except Exception as exc:  # pragma: no cover - defensive, never fatal # noqa: BLE001
        logger.warning("litellm langfuse callbacks skipped: %s", exc)


def get_langfuse_handler() -> Any | None:
    """A langfuse LangChain CallbackHandler, or None when it can't be built.

    Observability must never take the agent down: if langfuse is missing or
    unconfigured we return None and the graph simply runs without callbacks.
    """
    import os

    if not (os.getenv("LANGFUSE_PUBLIC_KEY") or os.getenv("LANGFUSE_MOCK")):
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception as exc:  # pragma: no cover - defensive, never fatal # noqa: BLE001
        logger.warning("langfuse CallbackHandler unavailable: %s", exc)
        return None


@dataclass
class ToolCall:
    """One tool invocation requested by the model (OpenAI `tool_calls` item)."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResult:
    """Normalized completion: plain text, tool calls, or both.

    `content` is the free-text part; `tool_calls` are structured invocations.
    A final answer has content and no tool_calls; an intermediate step in a
    tool loop has tool_calls and usually no content. `usage` carries the
    provider's token counts when available (observability, NFR-007).
    """

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = "unknown"
    usage: dict[str, Any] | None = None


class LLMClient(ABC):
    """Contract every LLM backend — LiteLLM, mock, local — must honour."""

    @abstractmethod
    def chat(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        model_tier: str = CHEAP_TIER,
        response_format: dict | None = None,
    ) -> LLMResult:
        """One completion call.

        Raises on any unrecoverable failure (timeout, rate limit, refusal, bad
        response). Callers decide what that means — the agents treat any
        exception as "fall through to the rule-based implementation".
        """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model actually serving requests, for logs and audit trails."""


class LiteLLMClient(LLMClient):
    """Production implementation: talks to the gateway via LiteLLM.

    `litellm.completion()` accepts an OpenAI-style message list, tool schemas,
    and `response_format` and routes to the configured model (which may be a
    LiteLLM proxy deployment). Keeping this adapter thin means the gateway
    config (virtual keys, budgets, failover) lives in LiteLLM's own config,
    not here.
    """

    def __init__(self, *, gateway_url: str = "", api_key: str = "", timeout_s: float = 30.0):
        self._gateway_url = gateway_url
        self._api_key = api_key
        self._timeout_s = timeout_s
        ensure_langfuse_wiring()

    def chat(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        model_tier: str = CHEAP_TIER,
        response_format: dict | None = None,
    ) -> LLMResult:
        from app.config import settings

        model = (
            settings.llm_frontier_model
            if model_tier == FRONTIER_TIER
            else settings.llm_cheap_model
        )
        if not model:
            raise RuntimeError(
                f"No model configured for tier {model_tier!r} — set "
                "LLM_CHEAP_MODEL / LLM_FRONTIER_MODEL"
            )

        import litellm

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "timeout": self._timeout_s,
        }
        if tools:
            kwargs["tools"] = tools
        if response_format:
            kwargs["response_format"] = response_format
        # Gateway override: when a URL is configured, everything routes through
        # it (virtual key auth). Otherwise the provider default is used.
        if self._gateway_url:
            kwargs["api_base"] = self._gateway_url
        if self._api_key:
            kwargs["api_key"] = self._api_key

        response = litellm.completion(**kwargs)
        message = response.choices[0].message

        tool_calls: list[ToolCall] = []
        for call in message.tool_calls or []:
            args: dict[str, Any] = {}
            try:
                import json

                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ToolCall(id=call.id, name=call.function.name, arguments=args)
            )

        usage: dict[str, Any] | None = None
        raw_usage = getattr(response, "usage", None)
        if raw_usage is not None:
            usage = {
                "prompt_tokens": getattr(raw_usage, "prompt_tokens", 0),
                "completion_tokens": getattr(raw_usage, "completion_tokens", 0),
                "total_tokens": getattr(raw_usage, "total_tokens", 0),
            }

        return LLMResult(
            content=message.content or "",
            tool_calls=tool_calls,
            model=getattr(response, "model", "") or model,
            usage=usage,
        )

    @property
    def model_name(self) -> str:
        from app.config import settings

        return settings.llm_frontier_model or settings.llm_cheap_model or "unknown"


class MockLLMClient(LLMClient):
    """Scripted client for tests and local dev. No network, no key, no cost.

    Each `chat()` call pops the next scripted response. When the script is
    exhausted it replays the last one, so a two-turn tool loop can be scripted
    as [tool-call turn, final turn] and any extra calls reuse the final turn —
    which is exactly what should happen if the graph behaved.
    """

    def __init__(
        self,
        responses: list[LLMResult | dict] | None = None,
        *,
        model: str = "mock-model",
        fail_every: int = 0,
    ):
        self._model = model
        self._script = [self._coerce(r, self._model) for r in (responses or [])]
        # Raise on every Nth call (0 = never). Lets tests exercise the fallback.
        self._fail_every = fail_every
        self._calls = 0

    @staticmethod
    def _coerce(response: LLMResult | dict, model: str) -> LLMResult:
        if isinstance(response, LLMResult):
            return response
        # Accept plain dicts for terser tests: {"content": ...} or {"tool_calls": [...]}
        content = str(response.get("content", ""))
        tool_calls = []
        for tc in response.get("tool_calls", []) or []:
            if isinstance(tc, ToolCall):
                tool_calls.append(tc)
            else:
                tool_calls.append(
                    ToolCall(
                        id=tc.get("id", "call_0"),
                        name=tc.get("name", ""),
                        arguments=tc.get("arguments", {}),
                    )
                )
        return LLMResult(content=content, tool_calls=tool_calls, model=model)

    def chat(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        model_tier: str = CHEAP_TIER,
        response_format: dict | None = None,
    ) -> LLMResult:
        self._calls += 1
        if self._fail_every and self._calls % self._fail_every == 0:
            raise TimeoutError("mock LLM timed out (scripted)")
        if not self._script:
            return LLMResult(model=self._model)
        return self._script[min(self._calls - 1, len(self._script) - 1)]

    @property
    def model_name(self) -> str:
        return self._model


class LiteLLMChatModel(BaseChatModel):
    """Adapter that exposes `LLMClient` to LangGraph as a BaseChatModel.

    This is the piece that lets the rest of the agent layer use stock
    LangGraph/LangChain primitives (`create_agent`, `ToolNode`, langfuse
    callbacks) instead of hand-wired plumbing: LangGraph drives the ReAct loop,
    and every turn funnels through this `_generate` into the same `LLMClient`
    seam (so the gateway/mock swap stays untouched).
    """

    model_name: str = "litellm-client"

    def __init__(
        self,
        client: LLMClient,
        *,
        model_tier: str = CHEAP_TIER,
        response_format: dict[str, Any] | None = None,
    ):
        super().__init__()
        self._client = client
        self._model_tier = model_tier
        self._tools: list[dict[str, Any]] = []
        self._tool_choice: Any = None
        self._response_format = response_format

    @property
    def _llm_type(self) -> str:
        return "litellm-client"

    def bind_tools(
        self,
        tools: Sequence[BaseTool | dict[str, Any]],
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> LiteLLMChatModel:
        # Store the tool schemas; `_generate` forwards them to the seam. Return
        # self (not a RunnableBinding) so state is applied on every turn — the
        # pattern LangGraph's `_should_bind_tools` expects.
        self._tools = [
            t if isinstance(t, dict) else convert_to_openai_tool(t) for t in tools
        ]
        self._tool_choice = tool_choice
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:
        # Structured output via litellm-native JSON-schema mode, then validate.
        schema_json = (
            schema.model_json_schema()
            if isinstance(schema, type)
            else schema
        )
        self._response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": getattr(schema, "__name__", "result"),
                "schema": schema_json,
            },
        }

        def _parse(message: AIMessage) -> Any:
            payload = json.loads(message.content or "{}")
            if isinstance(schema, type):
                return schema.model_validate(payload)
            return payload

        return self | RunnableLambda(_parse)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        result = self._client.chat(
            messages=convert_to_openai_messages(list(messages)),
            tools=self._tools or None,
            model_tier=self._model_tier,
            response_format=self._response_format,
        )
        tool_calls = [
            {"name": tc.name, "args": tc.arguments, "id": tc.id}
            for tc in result.tool_calls
        ]
        usage_metadata = None
        if result.usage:
            usage_metadata = {
                "input_tokens": result.usage.get("prompt_tokens", 0),
                "output_tokens": result.usage.get("completion_tokens", 0),
                "total_tokens": result.usage.get("total_tokens", 0),
            }
        message = AIMessage(
            content=result.content or "",
            tool_calls=tool_calls,
            usage_metadata=usage_metadata,
        )
        return ChatResult(generations=[ChatGeneration(message=message)])