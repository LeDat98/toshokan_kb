"""Single gateway to the Gemini API.

Convention (enforced by tests/test_conventions.py): no other module in `libkb`
may import `google.genai`. All calls log model, tokens and latency.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    # Opaque Gemini "thought signature" (bytes) that MUST be echoed back with the
    # function-call turn or the API rejects the next request (400). Not a genai type.
    thought_signature: Any = None


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
        model = model or self._settings.model
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
            except genai_errors.APIError as exc:
                last_exc = exc
                code = getattr(exc, "code", None)
                if attempt < max_retries and code in _RETRYABLE_CODES:
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
        """Structured output with one repair retry on invalid JSON."""
        result = self.generate(
            contents, model=model, system=system, json_schema=schema, temperature=temperature
        )
        try:
            return json.loads(result.text or "")
        except json.JSONDecodeError:
            log.warning("llm_json_repair", model=model or self._settings.model)
            repair = self.generate(
                "Return ONLY valid JSON matching the schema. Fix this output:\n"
                + (result.text or "<empty>"),
                model=model,
                json_schema=schema,
                temperature=0.0,
            )
            try:
                return json.loads(repair.text or "")
            except json.JSONDecodeError as exc:
                raise LLMError("structured output is not valid JSON after repair retry") from exc

    def embed(
        self, texts: list[str], *, task: str = "RETRIEVAL_DOCUMENT", model: str | None = None
    ) -> np.ndarray:
        """Returns L2-normalized float32 vectors, shape (len(texts), dim)."""
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        model = model or self._settings.embed_model
        vectors: list[list[float]] = []
        start = time.monotonic()
        for i in range(0, len(texts), _EMBED_BATCH):
            batch = texts[i : i + _EMBED_BATCH]
            try:
                response = self._client.models.embed_content(
                    model=model,
                    contents=batch,
                    config=genai_types.EmbedContentConfig(task_type=task),
                )
            except genai_errors.APIError as exc:
                raise LLMError(f"Gemini embed failed: {exc}") from exc
            vectors.extend(e.values for e in response.embeddings)
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
