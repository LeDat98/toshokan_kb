"""Single gateway to the model providers.

Convention (enforced by tests/test_conventions.py): no other module in `libkb` may import
`google.genai`. All calls log model, tokens and latency.

FOUR providers now: Gemini, Alibaba DashScope (Qwen) through its OpenAI-compatible endpoint, AWS
Bedrock (Anthropic), and Ollama (open-weight models, local or Ollama Cloud — one code path, because
the two differ only by host and bearer token). Routing is by MODEL NAME (`settings.*_prefixes`), so
`LIBKB_MODEL_LITE=qwen-flash` or `LIBKB_MODEL=ollama/gpt-oss:120b-cloud` is the entire
configuration — there is no second set of role flags to drift out of sync.

Deliberately NOT symmetric, and the asymmetry is the point:

  * generate_json + embed  → every provider. This is the bulk, cost-dominated work (the question
    flywheel at ingest), and it is exactly what a free quota should be spent on.
  * TOOL CALLING           → Gemini **and** DashScope (D-067); Bedrock and Ollama still raise.
    It was Gemini-only for a real reason: navigation is the one job we MEASURED a cheap model
    failing at (D-027: page 54% vs 86%), and Gemini's thought-signature protocol (D-017) has no
    equivalent elsewhere. But that argument is about the WALK — 9–13 turns, where a weak model's
    mistakes compound and are unrecoverable. The pool tools (D-066) are a handful of bounded calls
    over candidates the sieve already found, and refusing by provider made the 6×-cheaper tier
    untestable there. So the refusal is now a MEASUREMENT, not a rule. DashScope correlates results
    to calls by `tool_call_id`; that plumbing lives in `_dashscope_messages`.
"""

from __future__ import annotations

import copy
import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import structlog
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from libkb.config import get_settings
from libkb.exceptions import LLMError

log = structlog.get_logger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
_RETRYABLE_CODES = {429, 500, 502, 503, 504}
_EMBED_BATCH = 100
_DASHSCOPE_EMBED_BATCH = 10  # DashScope's per-request cap, not a tuning choice
# Ollama imposes no batch cap; this one bounds how much a single local model has to hold at once
# (and how much work one retry throws away), it is not a protocol limit.
_OLLAMA_EMBED_BATCH = 64


def _strip_code_fence(text: str) -> str:
    """Pull the body out of a ```json … ``` (or bare ```) fence. No-op if there is no fence."""
    t = text.strip()
    if not t.startswith("```"):
        return t
    t = re.sub(r"^```[a-zA-Z0-9]*\n?", "", t)
    return re.sub(r"\n?```\s*$", "", t).strip()


def _dashscope_messages(turn: Turn) -> list[dict[str, Any]]:
    """One neutral `Turn` → one OpenAI-shaped message (D-067).

    Three shapes, and the ORDER they must appear in is the protocol: an assistant message carrying
    `tool_calls`, then one `role="tool"` message per call echoing its `tool_call_id`. Omit the id
    and DashScope 400s the *next* request, not this one — which reads as a random failure several
    turns later. `call_id` is the neutral `ToolCall`'s own field, so the round-trip is closed here
    rather than left to each caller."""
    if turn.tool_calls:
        return [
            {
                "role": "assistant",
                "content": turn.text or "",
                "tool_calls": [
                    {
                        "id": call.call_id or call.name,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.args or {})},
                    }
                    for call in turn.tool_calls
                ],
            }
        ]
    if turn.tool_responses:
        # OpenAI wants ONE message per tool result, so a Turn batching several fans out here.
        return [
            {
                "role": "tool",
                "tool_call_id": r.call_id or r.name,
                "content": json.dumps(r.response, ensure_ascii=False),
            }
            for r in turn.tool_responses
        ]
    return [{"role": "assistant" if turn.role == "model" else "user", "content": turn.text or ""}]


def _dashscope_tool_calls(message: Any) -> list[ToolCall]:
    """The provider's tool calls → the neutral `ToolCall`. Arguments arrive as a JSON *string*; a
    model that emits malformed JSON must cost one call, not crash the loop, so a bad payload
    degrades to empty args and the tool layer rejects it with a message the model can act on."""
    out: list[ToolCall] = []
    for raw in getattr(message, "tool_calls", None) or []:
        fn = getattr(raw, "function", None)
        if fn is None:
            continue
        try:
            args = json.loads(fn.arguments or "{}")
        except (TypeError, ValueError):
            args = {}
        out.append(
            ToolCall(name=fn.name, args=args if isinstance(args, dict) else {}, call_id=raw.id)
        )
    return out


def _is_retryable(exc: Exception) -> bool:
    """The OpenAI SDK's exception tree is not importable from here (it is an optional dep), so the
    status code is read off the exception rather than matched by type."""
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if code is None:
        resp = getattr(exc, "response", None)
        if isinstance(resp, dict):
            # botocore's ClientError carries the HTTP status inside .response, not as an attribute
            code = resp.get("ResponseMetadata", {}).get("HTTPStatusCode")
        else:
            # httpx.HTTPStatusError (the Ollama path) carries a Response object there instead
            code = getattr(resp, "status_code", None)
    try:
        return int(code) in _RETRYABLE_CODES
    except (TypeError, ValueError):
        return False


def _ollama_think(value: str) -> bool | str | None:
    """Map the `LIBKB_OLLAMA_THINK` string onto what `/api/chat` expects. Empty ⇒ None ⇒ the field
    is not sent at all, which leaves the model's own default in place."""
    v = (value or "").strip().lower()
    if not v:
        return None
    if v in {"false", "0", "no", "off"}:
        return False
    if v in {"true", "1", "yes", "on"}:
        return True
    return v  # "low" | "medium" | "high" | "max"


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    # Opaque Gemini "thought signature" (bytes) that MUST be echoed back with the
    # function-call turn or the API rejects the next request (400). Not a genai type.
    thought_signature: Any = None
    # OpenAI-shaped providers (DashScope, D-067) correlate a result to its call by id, and reject
    # the NEXT request if it is missing — a failure that surfaces turns later. Gemini has no
    # counterpart and leaves it None, so the field is additive, not a second protocol.
    call_id: str | None = None


@dataclass
class ToolSpec:
    """A function the model may call. `parameters` is a JSON-schema object."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolResponse:
    name: str
    response: dict[str, Any]
    call_id: str | None = None  # echoed back to OpenAI-shaped providers; see ToolCall.call_id


@dataclass
class Turn:
    """One conversation turn in the neutral (genai-free) message format."""

    role: str  # "user" | "model" | "tool"
    text: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_responses: list[ToolResponse] | None = None


@dataclass
class Usage:
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


@dataclass
class LLMResult:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None


class LLM:
    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self._settings = settings
        self._client = genai.Client(api_key=api_key or settings.gemini_api_key)
        self._dashscope: Any = None  # built lazily: the SDK is optional and the key may be absent
        self._bedrock: Any = None  # built lazily: boto3 is optional, reads ~/.aws itself
        self._ollama: Any = None  # built lazily: an httpx.Client, so connections are pooled
        self.default_model: str | None = None  # None ⇒ settings.model
        # Monotonic counters, not a log — the eval diffs them around each case to price a query
        # (ROUTING_REDESIGN §3.0). Ints, so a long-lived API process cannot grow a list forever.
        # `+=` on an int is a read-modify-write, so a concurrent eval (backlog #1) could lose
        # updates without this lock — an undercount is a lie about cost, cheap to prevent.
        self._token_lock = threading.Lock()
        self.n_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        # per-model input tokens, so a two-tier query (cheap selector + strong answerer) can be
        # PRICED correctly — the aggregate counter cannot tell a lite token from a flash one.
        self.input_by_model: dict[str, int] = {}

    def _record_usage(self, usage: Usage) -> None:
        """Bump the monotonic counters atomically — safe under a concurrent eval/ingest pool."""
        with self._token_lock:
            self.n_calls += 1
            self.total_input_tokens += usage.input_tokens
            self.total_output_tokens += usage.output_tokens
            self.input_by_model[usage.model] = (
                self.input_by_model.get(usage.model, 0) + usage.input_tokens
            )

    def with_model(self, model: str | None) -> LLM:
        """A view of this client that answers on a different model. Switching costs nothing.

        The model a query runs on is a property of the QUERY, not of the process. Reaching for a
        global — mutating `settings.model`, rebuilding the singleton — would make two concurrent
        requests fight over one variable and would force a reload to take effect. So instead the
        API clones the client (the underlying HTTP clients are shared; only the default model and
        the token counters differ) and hands it down the call chain, which every layer already
        accepts as `llm=`.

        NOTE the counters are per-view on purpose: a caller that wants to price one query can diff
        them without another request's tokens leaking into the total.
        """
        if not model or model == (self.default_model or self._settings.model):
            return self
        clone = copy.copy(self)
        clone.default_model = model
        clone.n_calls = 0
        clone.total_input_tokens = 0
        clone.total_output_tokens = 0
        clone.input_by_model = {}
        return clone

    # ------------------------------------------------------------------ provider routing
    def _is_dashscope(self, model: str) -> bool:
        return model.startswith(tuple(self._settings.dashscope_prefixes))

    def _is_bedrock(self, model: str) -> bool:
        return model.startswith(tuple(self._settings.bedrock_prefixes))

    def _bedrock_client(self) -> Any:
        """boto3 bedrock-runtime client. Lazy: boto3 is optional. Credentials + region come from the
        standard AWS chain (env vars, ~/.aws/credentials, ~/.aws/config) that boto3 reads ITSELF —
        we never open that file. Region falls back to config only if the AWS profile sets none."""
        if self._bedrock is None:
            try:
                import boto3  # noqa: PLC0415 — optional dep, imported only for a Bedrock model
                from botocore.config import Config
            except ImportError as exc:  # pragma: no cover - dep guard
                raise LLMError("Bedrock needs boto3 (pip install boto3)") from exc
            self._bedrock = boto3.client(
                "bedrock-runtime",
                region_name=self._settings.bedrock_region,
                # own the retry loop (_generate_bedrock); a per-call timeout turns a hung socket
                # into a fast retryable failure instead of freezing the run (as with DashScope).
                config=Config(retries={"max_attempts": 0}, read_timeout=60, connect_timeout=10),
            )
        return self._bedrock

    def _is_ollama(self, model: str) -> bool:
        return model.startswith(self._settings.ollama_prefix)

    def _ollama_model(self, model: str) -> str:
        """`ollama/gpt-oss:120b-cloud` → `gpt-oss:120b-cloud`. The prefix is OUR routing token, not
        part of the model's name, and Ollama would 404 on it."""
        return model[len(self._settings.ollama_prefix) :]

    def provider_of(self, model: str | None = None) -> str:
        """Which provider a model id routes to. One place, so the API's picker cannot drift out of
        sync with what `generate` actually does (it used to label every non-Gemini model
        'dashscope' and gate its availability on the DashScope key)."""
        m = model or self.default_model or self._settings.model
        if self._is_ollama(m):
            return "ollama"
        if self._is_dashscope(m):
            return "dashscope"
        if self._is_bedrock(m):
            return "bedrock"
        return "gemini"

    def supports_tools(self, model: str | None = None) -> bool:
        """Tool calling is Gemini-only (see the module docstring). The UI needs to know BEFORE the
        user picks, not after the walk dies halfway through."""
        return self.provider_of(model) == "gemini"

    def _dashscope_client(self) -> Any:
        """OpenAI-compatible client for DashScope. Imported lazily so `openai` stays optional."""
        if self._dashscope is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - dep guard
                raise LLMError("Qwen/DashScope needs the openai SDK (pip install openai)") from exc
            if not self._settings.dashscope_api_key:
                raise LLMError("DASHSCOPE_API_KEY is not set — cannot call a qwen model")
            self._dashscope = OpenAI(
                api_key=self._settings.dashscope_api_key,
                base_url=f"https://{self._settings.dashscope_host}/compatible-mode/v1",
                # A REQUEST MUST TIME OUT, or a hung socket blocks the whole run. The OpenAI SDK
                # defaults to 600s per request — MEASURED: a hung DashScope socket froze a 301-case
                # eval for 30 minutes at 0% CPU, because `_with_retry` never fires until the request
                # returns, and the request was still "waiting". 60s is generous for a chat/embed
                # call and turns a dead socket into a fast, retryable failure.
                timeout=60.0,
                max_retries=0,  # we own the retry loop (_with_retry); the SDK must not double it
            )
        return self._dashscope

    def _ollama_client(self) -> Any:
        """One pooled `httpx.Client` for Ollama. No SDK: Ollama's native API is a handful of JSON
        POSTs, and httpx is already a hard dependency — so unlike DashScope (openai) and Bedrock
        (boto3) this provider adds nothing to install.

        LOCAL and CLOUD are the same client. `LIBKB_OLLAMA_HOST=https://ollama.com` +
        `OLLAMA_API_KEY` points it at Ollama Cloud; the default points it at the local daemon,
        which ignores the (absent) bearer token. There is no second code path to keep in sync.
        """
        if self._ollama is None:
            host = self._settings.ollama_host.rstrip("/")
            headers = {"Content-Type": "application/json"}
            if self._settings.ollama_api_key:
                headers["Authorization"] = f"Bearer {self._settings.ollama_api_key}"
            self._ollama = httpx.Client(
                base_url=host,
                headers=headers,
                # A cold local model LOADS before it answers and a big cloud model thinks for a
                # while, so the read budget is generous — but a connect timeout stays short: a
                # daemon that is not running should fail in seconds, not in three minutes.
                timeout=httpx.Timeout(self._settings.ollama_timeout, connect=10.0),
            )
        return self._ollama

    def _ollama_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._ollama_client().post(path, json=payload)
        response.raise_for_status()
        return response.json()

    def generate(
        self,
        contents: str | list[Turn],
        *,
        model: str | None = None,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        json_schema: Any | None = None,
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> LLMResult:
        model = model or self.default_model or self._settings.model
        if self._is_dashscope(model):
            return self._generate_dashscope(
                contents,
                model=model,
                system=system,
                tools=tools,
                json_schema=json_schema,
                temperature=temperature,
                max_retries=max_retries,
            )
        if self._is_bedrock(model):
            return self._generate_bedrock(
                contents,
                model=model,
                system=system,
                tools=tools,
                json_schema=json_schema,
                temperature=temperature,
                max_retries=max_retries,
            )
        if self._is_ollama(model):
            return self._generate_ollama(
                contents,
                model=model,
                system=system,
                tools=tools,
                json_schema=json_schema,
                temperature=temperature,
                max_retries=max_retries,
            )
        config = genai_types.GenerateContentConfig(temperature=temperature)
        if system:
            config.system_instruction = system
        if tools:
            config.tools = _to_genai_tools(tools)
            # we handle the tool loop ourselves (budgets, events, isolated context)
            config.automatic_function_calling = genai_types.AutomaticFunctionCallingConfig(
                disable=True
            )
        if json_schema is not None:
            config.response_mime_type = "application/json"
            config.response_schema = json_schema

        genai_contents = _to_genai_contents(contents)
        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            start = time.monotonic()
            try:
                response = self._client.models.generate_content(
                    model=model, contents=genai_contents, config=config
                )
                return self._to_result(response, model, int((time.monotonic() - start) * 1000))
            except (genai_errors.APIError, httpx.TransportError) as exc:
                # httpx.TransportError too: a dropped socket is not an API verdict, and if it is not
                # wrapped in LLMError it escapes `answer_query_safe` and kills the whole run.
                last_exc = exc
                code = getattr(exc, "code", None)
                retryable = code in _RETRYABLE_CODES or isinstance(exc, httpx.TransportError)
                if attempt < max_retries and retryable:
                    log.warning(
                        "llm_retry", model=model, code=code, attempt=attempt + 1, delay_s=delay
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise LLMError(f"Gemini call failed (code={code}): {exc}") from exc
        raise LLMError(f"Gemini call failed after {max_retries} retries") from last_exc

    def generate_json(
        self,
        contents: Any,
        *,
        schema: Any,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> Any:
        """Structured output. A bad response is RE-ASKED, never "repaired", and a call that will not
        come back clean raises — it does not return a half-answer.

        **This used to fail OPEN, and it invented answers.** The old path took a malformed response
        and asked the model to *fix this output*. A truncated `{"answer": "J` is not a formatting
        problem — it is a call that did not happen. Asking a model to repair that fragment is asking
        it to hallucinate the rest, and it obliged: MEASURED on 301 unanswerable MultiHop questions,
        **40 of them came back with a ONE-CHARACTER answer** (`"J"`, `"F"`, `"X"`) carrying an
        invented `"sufficient": true`. The library had nothing to say, and the repair path made
        something up on its behalf — the precise failure P6 exists to forbid.

        So: re-ask the ORIGINAL question (the model gets another go at answering, not at
        rationalising a fragment), validate the required keys, and if it still will not comply,
        **raise**. `answer_query_safe` turns an LLMError into an honest NOT_FOUND, which is the only
        safe direction for this to fail in.
        """
        required = list(schema.get("required", [])) if isinstance(schema, dict) else []

        def parse(text: str | None) -> Any | None:
            try:
                data = json.loads(text or "")
            except json.JSONDecodeError:
                return None
            # a bare string/number is valid JSON and is NOT the object we asked for
            if not isinstance(data, dict) or any(key not in data for key in required):
                return None
            return data

        result = self.generate(
            contents, model=model, system=system, json_schema=schema, temperature=temperature
        )
        data = parse(result.text)
        if data is not None:
            return data

        log.warning("llm_json_retry", model=model or self.default_model or self._settings.model)
        retry = self.generate(
            contents,  # the same question, not "fix your last answer"
            model=model,
            system=system,
            json_schema=schema,
            temperature=temperature,
        )
        data = parse(retry.text)
        if data is None:
            raise LLMError(
                "the model did not return a JSON object with the required keys "
                f"({', '.join(required) or 'any'}) after a retry"
            )
        return data

    def _generate_dashscope(
        self,
        contents: str | list[Turn],
        *,
        model: str,
        system: str | None,
        tools: list[ToolSpec] | None,
        json_schema: Any | None,
        temperature: float,
        max_retries: int,
    ) -> LLMResult:
        # TOOL CALLING (D-067). This used to refuse outright, on the grounds that navigation is the
        # one job a cheaper model measurably failed at (D-027) and that Gemini's thought-signature
        # echo (D-017) has no counterpart here. Both facts still hold — but they are an argument
        # about the WALK, whose 9–13 turns compound a weak model's mistakes. The pool tools (D-066)
        # are a different shape: a handful of bounded calls over 50–100 candidates the sieve already
        # found, where a wrong tool call costs one cheap call and is visible in the trace. Refusing
        # by provider made that untestable on the tier that is 6× cheaper, so the refusal is gone
        # and the question is handed back to measurement, where it belongs.
        client = self._dashscope_client()
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if isinstance(contents, str):
            messages.append({"role": "user", "content": contents})
        else:
            for turn in contents:
                messages.extend(_dashscope_messages(turn))

        kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.parameters,
                    },
                }
                for spec in tools
            ]
        if json_schema is not None:
            # Qwen honours `json_object` but does NOT enforce a schema server-side the way Gemini
            # does, so the schema has to travel in the prompt — and `generate_json`'s repair retry
            # stops being a formality and becomes the actual guarantee.
            kwargs["response_format"] = {"type": "json_object"}
            messages[-1]["content"] += (
                "\n\nReturn ONLY a JSON object matching this schema — no prose, no code fence:\n"
                + json.dumps(json_schema, ensure_ascii=False)
            )

        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            start = time.monotonic()
            try:
                response = client.chat.completions.create(**kwargs)
            except Exception as exc:  # the OpenAI SDK's error tree is not importable here
                last_exc = exc
                if attempt < max_retries and _is_retryable(exc):
                    log.warning("llm_retry", model=model, attempt=attempt + 1, delay_s=delay)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise LLMError(f"DashScope call failed: {exc}") from exc
            # A REFUSAL IS NOT A RESPONSE. DashScope returns `choices: null` when its content filter
            # trips — no error, no status code, no message. MEASURED on the MultiHop corpus: Qwen
            # refuses to summarise a news article about the Epoch Times (a paper critical of the
            # Chinese government) that Gemini handles without comment. Unguarded, that surfaced as a
            # raw `TypeError: 'NoneType' object is not subscriptable`, which the caller logged and
            # swallowed — so the page silently left the corpus.
            #
            # This is a DATA-INTEGRITY property of the provider, not a bug we can fix: choose a
            # model whose refusals you can live with, and make sure they are LOUD when they happen.
            if not getattr(response, "choices", None):
                raise LLMError(
                    f"{model} returned no choices — DashScope's content filter refuses some "
                    f"material outright (it does so silently). This page cannot be indexed by "
                    f"this model; use a Gemini model for it."
                )
            usage = Usage(
                model=model,
                input_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
                latency_ms=int((time.monotonic() - start) * 1000),
            )
            self._record_usage(usage)
            message = response.choices[0].message
            calls = _dashscope_tool_calls(message)
            log.info(
                "llm_call",
                model=model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                latency_ms=usage.latency_ms,
                tool_calls=len(calls),
            )
            # Mirror the Gemini path: a turn that called a tool carries no text. Qwen sometimes
            # returns an empty string alongside its calls, and a caller that trusted `text` would
            # treat "" as an answer and stop the loop.
            text = None if calls else message.content
            return LLMResult(text=text, tool_calls=calls, usage=usage)
        raise LLMError("DashScope call failed after retries") from last_exc

    def _generate_bedrock(
        self,
        contents: str | list[Turn],
        *,
        model: str,
        system: str | None,
        tools: list[ToolSpec] | None,
        json_schema: Any | None,
        temperature: float,
        max_retries: int,
    ) -> LLMResult:
        """Answer/triage on an Anthropic model via the Bedrock Converse API. Tool-calling stays on
        Gemini (D-016/D-017): the navigator's loop echoes Gemini thought-signatures, which have no
        Bedrock counterpart, so a silent fallback would move the hardest job to an untested path."""
        if tools:
            raise LLMError(
                f"tool calling is Gemini-only; {model} is a Bedrock model. "
                "Keep navigation on Gemini and send only answer/triage to Bedrock."
            )
        client = self._bedrock_client()
        messages: list[dict[str, Any]] = []
        if isinstance(contents, str):
            user_text = contents
            messages.append({"role": "user", "content": [{"text": contents}]})
        else:
            for turn in contents:
                if turn.tool_calls or turn.tool_responses:
                    raise LLMError("Bedrock path carries no tool turns")
                role = "assistant" if turn.role == "model" else "user"
                messages.append({"role": role, "content": [{"text": turn.text or ""}]})
            user_text = messages[-1]["content"][0]["text"] if messages else ""

        if json_schema is not None:
            # Like DashScope: no server-side schema enforcement, so the schema rides in the prompt
            # and `generate_json`'s retry is the real guarantee. Anthropic honours a JSON request.
            messages[-1]["content"][0]["text"] = user_text + (
                "\n\nReturn ONLY a JSON object matching this schema — no prose, no code fence:\n"
                + json.dumps(json_schema, ensure_ascii=False)
            )

        kwargs: dict[str, Any] = {
            "modelId": model,
            "messages": messages,
            "inferenceConfig": {"temperature": temperature, "maxTokens": 4096},
        }
        if system:
            kwargs["system"] = [{"text": system}]

        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            start = time.monotonic()
            try:
                response = client.converse(**kwargs)
            except Exception as exc:  # botocore's error tree is not importable at module top
                last_exc = exc
                if attempt < max_retries and _is_retryable(exc):
                    log.warning("llm_retry", model=model, attempt=attempt + 1, delay_s=delay)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise LLMError(f"Bedrock call failed: {exc}") from exc
            parts = response.get("output", {}).get("message", {}).get("content", [])
            text = "".join(p.get("text", "") for p in parts)
            if json_schema is not None:
                # Anthropic wraps structured output in a ```json fence even when asked not to; strip
                # it so `generate_json`'s json.loads sees the object. JSON path only — a free-text
                # answer may legitimately contain a code block.
                text = _strip_code_fence(text)
            u = response.get("usage", {})
            usage = Usage(
                model=model,
                input_tokens=int(u.get("inputTokens", 0) or 0),
                output_tokens=int(u.get("outputTokens", 0) or 0),
                latency_ms=int((time.monotonic() - start) * 1000),
            )
            self._record_usage(usage)
            log.info(
                "llm_call",
                model=model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                latency_ms=usage.latency_ms,
                tool_calls=0,
            )
            return LLMResult(text=text, usage=usage)
        raise LLMError("Bedrock call failed after retries") from last_exc

    def _generate_ollama(
        self,
        contents: str | list[Turn],
        *,
        model: str,
        system: str | None,
        tools: list[ToolSpec] | None,
        json_schema: Any | None,
        temperature: float,
        max_retries: int,
    ) -> LLMResult:
        """Open-weight models through Ollama — the same code for a local daemon and for the cloud.

        Two things here are BETTER than the other non-Gemini providers, and both are structural
        rather than a matter of model quality:

          * **The JSON schema is enforced server-side.** `format: <schema>` constrains decoding, so
            the reply cannot be the malformed shape that cost us 21% of a corpus on DashScope
            (D-040). `generate_json` still validates and re-asks — a model can satisfy a schema and
            still say nothing useful — but the failure mode it guards against becomes rare here.
          * **Thinking is a knob we hold.** Most Ollama cloud models reason by default; on a triage
            or question-generation call that is pure cost. Off by default (`LIBKB_OLLAMA_THINK`).

        Tool calling is refused, as for DashScope and Bedrock — even though Ollama models DO
        advertise tools. The walk echoes Gemini thought-signatures (D-017), which have no
        counterpart here, and navigation is the one job a cheap model MEASURABLY fails (D-027).
        The cascade — the default retrieval path — is tool-free, so any Ollama model can run it.
        """
        if tools:
            raise LLMError(
                f"tool calling is Gemini-only; {model} is an Ollama model. "
                "Keep LIBKB_MODEL on Gemini for the tree-walk; the cascade (the default) is "
                "tool-free and runs on any provider."
            )
        name = self._ollama_model(model)
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if isinstance(contents, str):
            messages.append({"role": "user", "content": contents})
        else:
            for turn in contents:
                if turn.tool_calls or turn.tool_responses:
                    raise LLMError("Ollama path carries no tool turns")
                role = "assistant" if turn.role == "model" else "user"
                messages.append({"role": role, "content": turn.text or ""})

        payload: dict[str, Any] = {
            "model": name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_schema is not None:
            payload["format"] = json_schema
        think = _ollama_think(self._settings.ollama_think)
        if think is not None:
            payload["think"] = think

        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            start = time.monotonic()
            try:
                data = self._ollama_post("/api/chat", payload)
            except httpx.HTTPStatusError as exc:
                # A model with no reasoning mode rejects `think` outright (400). That is a property
                # of the MODEL, not of the request we meant to make, so drop the field and go on
                # rather than making every non-thinking model unusable through this path.
                last_exc = exc
                if "think" in payload and exc.response.status_code == 400:
                    body = exc.response.text.lower()
                    if "think" in body or "thinking" in body:
                        log.info("ollama_think_unsupported", model=name)
                        payload.pop("think")
                        continue
                if attempt < max_retries and _is_retryable(exc):
                    log.warning("llm_retry", model=name, attempt=attempt + 1, delay_s=delay)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise LLMError(f"Ollama call failed ({exc.response.status_code}): {exc}") from exc
            except httpx.HTTPError as exc:  # transport: daemon down, socket dropped, timeout
                last_exc = exc
                if attempt < max_retries:
                    log.warning("llm_retry", model=name, attempt=attempt + 1, delay_s=delay)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise LLMError(f"Ollama call failed: {exc}") from exc

            message = data.get("message") or {}
            text = message.get("content") or ""
            # FAIL CLOSED. An empty content is not an answer, and the two ways to get one here are
            # both silent: a model that spent its whole budget inside `thinking`, and a refusal that
            # Ollama reports as a normal 200. Either way the caller must see a failure, not "".
            if not text.strip():
                raise LLMError(
                    f"{name} returned an empty message (done_reason="
                    f"{data.get('done_reason')!r}). If it is a thinking model, its reasoning may "
                    "have consumed the whole budget — raise num_predict or set LIBKB_OLLAMA_THINK."
                )
            if json_schema is not None:
                # Constrained decoding should make this a no-op; a small model asked for JSON in
                # the prompt (rather than by schema) still sometimes fences it.
                text = _strip_code_fence(text)
            usage = Usage(
                model=model,
                input_tokens=int(data.get("prompt_eval_count") or 0),
                output_tokens=int(data.get("eval_count") or 0),
                latency_ms=int((time.monotonic() - start) * 1000),
            )
            self._record_usage(usage)
            log.info(
                "llm_call",
                model=model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                latency_ms=usage.latency_ms,
                tool_calls=0,
            )
            return LLMResult(text=text, usage=usage)
        raise LLMError("Ollama call failed after retries") from last_exc

    def embed(
        self, texts: list[str], *, task: str = "RETRIEVAL_DOCUMENT", model: str | None = None
    ) -> np.ndarray:
        """Returns L2-normalized float32 vectors, shape (len(texts), dim).

        ⚠️ The model that produced a vector is part of the vector's MEANING. Two embedders are two
        coordinate systems, and a cosine across them is not a worse number — it is not a number.
        Never populate one catalog from two embedders; reindex whole or not at all.
        """
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        model = model or self._settings.embed_model
        # An empty string is a valid row of a corpus and an INVALID embedding request: Gemini rejects
        # the whole batch with "content contains an empty Part", and one blank document (FiQA has
        # them) killed a 57k-document run at doc 500. A blank doc IS irrelevant to every query, so a
        # placeholder vector — which matches nothing — is the correct, alignment-preserving fix.
        texts = [t if t and t.strip() else "(empty)" for t in texts]
        start = time.monotonic()
        if self._is_dashscope(model):
            vectors = self._embed_dashscope(texts, model)
        elif self._is_ollama(model):
            vectors = self._embed_ollama(texts, model, task)
        else:
            vectors = self._embed_gemini(texts, model, task)
        log.info(
            "llm_embed",
            model=model,
            n_texts=len(texts),
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        array = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(array, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return array / norms

    def _with_retry(self, call: Callable[[], Any], what: str) -> Any:
        """Embedding had NO retry and leaked raw transport errors, and both halves of that hurt.

        `generate` retries three times; `embed` retried zero, and caught only `genai_errors.APIError`
        — so an `httpx.RemoteProtocolError` ("Server disconnected without sending a response") sailed
        straight past `answer_query_safe`, which catches `LLMError`, and killed a 301-case eval after
        hundreds of paid queries. A transient socket is not an answer about the library; it must look
        like a retryable failure and then, if it persists, like an LLMError.
        """
        delay = 1.0
        for attempt in range(4):
            try:
                return call()
            except Exception as exc:
                retryable = _is_retryable(exc) or isinstance(exc, httpx.TransportError)
                if attempt < 3 and retryable:
                    log.warning("embed_retry", what=what, attempt=attempt + 1, error=str(exc)[:80])
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise LLMError(f"{what} failed: {exc}") from exc
        raise LLMError(f"{what} failed after retries")

    def _embed_gemini(self, texts: list[str], model: str, task: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH):
            batch = texts[i : i + _EMBED_BATCH]
            response = self._with_retry(
                lambda b=batch: self._client.models.embed_content(
                    model=model,
                    contents=b,
                    config=genai_types.EmbedContentConfig(task_type=task),
                ),
                "Gemini embed",
            )
            vectors.extend(e.values for e in response.embeddings)
        return vectors

    def _embed_dashscope(self, texts: list[str], model: str) -> list[list[float]]:
        # DashScope's embedding endpoint caps a request far below Gemini's 100; the small batch is
        # not a tuning choice, it is the API's limit.
        client = self._dashscope_client()
        vectors: list[list[float]] = []
        for i in range(0, len(texts), _DASHSCOPE_EMBED_BATCH):
            batch = texts[i : i + _DASHSCOPE_EMBED_BATCH]
            response = self._with_retry(
                lambda b=batch: client.embeddings.create(model=model, input=b),
                "DashScope embed",
            )
            vectors.extend(item.embedding for item in response.data)
        return vectors

    def _embed_ollama(self, texts: list[str], model: str, task: str) -> list[list[float]]:
        """Embeddings on an open-weight model. NOTE this is a LOCAL capability: Ollama Cloud hosts
        chat models only, so `LIBKB_EMBED_MODEL=ollama/…` needs a daemon on this machine (which is
        fine — an embedder is 0.3–0.6B and runs on CPU).

        Ollama has no `task_type`, so gemini's document/query asymmetry is expressed the way open
        embedders express it: an instruction prefix on the QUERY side only. The wording differs per
        model, so it is configuration (`ollama_embed_query_prefix`), not a guess made here. Left
        empty the embedding is symmetric — correct for bge-m3, a small quality loss for the models
        that were trained with a prefix.
        """
        name = self._ollama_model(model)
        prefix = self._settings.ollama_embed_query_prefix if "QUERY" in (task or "").upper() else ""
        vectors: list[list[float]] = []
        for i in range(0, len(texts), _OLLAMA_EMBED_BATCH):
            batch = [prefix + t for t in texts[i : i + _OLLAMA_EMBED_BATCH]]
            data = self._with_retry(
                lambda b=batch: self._ollama_post("/api/embed", {"model": name, "input": b}),
                "Ollama embed",
            )
            got = data.get("embeddings") or []
            if len(got) != len(batch):
                # An alignment break is silent and poisonous: row i would carry row j's vector and
                # every cosine after it is meaningless. Fail loudly instead.
                raise LLMError(
                    f"Ollama embed returned {len(got)} vectors for {len(batch)} inputs ({name})"
                )
            vectors.extend(got)
        return vectors

    def load_prompt(self, name: str, **variables: object) -> str:
        """Load prompts/<name>.md and substitute {{var}} placeholders (brace-safe)."""
        text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
        for key, value in variables.items():
            text = text.replace("{{" + key + "}}", str(value))
        return text

    def _to_result(self, response: Any, model: str, latency_ms: int) -> LLMResult:
        # iterate parts (not response.function_calls) so we can capture each call's
        # thought_signature, which must be echoed back on the next turn (Gemini 3+)
        tool_calls: list[ToolCall] = []
        candidate = response.candidates[0] if response.candidates else None
        if candidate and candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if getattr(part, "function_call", None):
                    fc = part.function_call
                    tool_calls.append(
                        ToolCall(
                            name=fc.name,
                            args=dict(fc.args or {}),
                            thought_signature=getattr(part, "thought_signature", None),
                        )
                    )
        text = None if tool_calls else response.text
        meta = response.usage_metadata
        usage = Usage(
            model=model,
            input_tokens=(meta.prompt_token_count or 0) if meta else 0,
            output_tokens=(meta.candidates_token_count or 0) if meta else 0,
            latency_ms=latency_ms,
        )
        self._record_usage(usage)
        log.info(
            "llm_call",
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=latency_ms,
            tool_calls=len(tool_calls),
        )
        return LLMResult(text=text, tool_calls=tool_calls, usage=usage)


# --------------------------------------------------- neutral → genai translation

_SCHEMA_TYPES = {
    "object": "OBJECT",
    "string": "STRING",
    "array": "ARRAY",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
}


def _to_genai_schema(node: dict[str, Any]) -> genai_types.Schema:
    kind = node.get("type", "string")
    kwargs: dict[str, Any] = {"type": _SCHEMA_TYPES.get(kind, "STRING")}
    if "description" in node:
        kwargs["description"] = node["description"]
    if "enum" in node:
        kwargs["enum"] = node["enum"]
    if kind == "object":
        kwargs["properties"] = {
            key: _to_genai_schema(sub) for key, sub in node.get("properties", {}).items()
        }
        if node.get("required"):
            kwargs["required"] = node["required"]
    if kind == "array" and "items" in node:
        kwargs["items"] = _to_genai_schema(node["items"])
    return genai_types.Schema(**kwargs)


def _to_genai_tools(tools: list[ToolSpec]) -> list[genai_types.Tool]:
    declarations = [
        genai_types.FunctionDeclaration(
            name=spec.name,
            description=spec.description,
            parameters=_to_genai_schema(spec.parameters),
        )
        for spec in tools
    ]
    return [genai_types.Tool(function_declarations=declarations)]


def _to_genai_contents(contents: str | list[Turn]) -> Any:
    if isinstance(contents, str):
        return contents
    result: list[genai_types.Content] = []
    for turn in contents:
        if turn.role == "tool":
            parts = [
                genai_types.Part(
                    function_response=genai_types.FunctionResponse(
                        name=tr.name, response=tr.response
                    )
                )
                for tr in (turn.tool_responses or [])
            ]
            # Gemini requires function responses in a user-role content
            result.append(genai_types.Content(role="user", parts=parts))
        elif turn.role == "model" and turn.tool_calls:
            parts = []
            for tc in turn.tool_calls:
                part = genai_types.Part(
                    function_call=genai_types.FunctionCall(name=tc.name, args=tc.args)
                )
                if tc.thought_signature is not None:
                    part.thought_signature = tc.thought_signature
                parts.append(part)
            result.append(genai_types.Content(role="model", parts=parts))
        else:
            role = "model" if turn.role == "model" else "user"
            result.append(
                genai_types.Content(role=role, parts=[genai_types.Part(text=turn.text or "")])
            )
    return result


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm
