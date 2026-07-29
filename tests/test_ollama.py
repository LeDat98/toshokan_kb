"""Ollama provider — routing, the native-API request shape, and the fail-closed guarantees.

LLM-free by construction: every test drives `_ollama_post` through a stub, so the suite never needs
a daemon, a key, or a network. What is asserted is the CONTRACT with Ollama's `/api/chat` and
`/api/embed` (the fields we send, the fields we read) plus the two properties that are load-bearing
for this project — a broken call fails CLOSED, and an alignment break in a batch of embeddings is
loud rather than silent.
"""

from typing import Any

import httpx
import numpy as np
import pytest

from libkb.config import Settings
from libkb.exceptions import LLMError
from libkb.llm.client import LLM, Turn, _ollama_think


class FakeLLM(LLM):
    """An LLM whose only real behaviour is provider routing — no genai client is constructed."""

    def __init__(self, settings: Settings, replies: list[Any] | None = None) -> None:
        self._settings = settings
        self._client = None
        self._dashscope = None
        self._bedrock = None
        self._ollama = None
        self.default_model = None
        import threading

        self._token_lock = threading.Lock()
        self.n_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.input_by_model: dict[str, int] = {}
        self.posts: list[tuple[str, dict]] = []
        self._replies = list(replies or [])

    def _ollama_post(self, path: str, payload: dict) -> dict:
        # a COPY: the retry path mutates the live payload (it drops `think`), and recording the
        # reference would rewrite history and make the assertion below unfalsifiable
        self.posts.append((path, dict(payload)))
        reply = self._replies.pop(0) if self._replies else {}
        if isinstance(reply, Exception):
            raise reply
        return reply


def settings(**overrides: Any) -> Settings:
    base = {"GEMINI_API_KEY": "k", **overrides}
    return Settings(_env_file=None, **base)


def chat_reply(content: str, *, prompt_tokens: int = 11, eval_tokens: int = 7) -> dict:
    return {
        "message": {"role": "assistant", "content": content},
        "done_reason": "stop",
        "prompt_eval_count": prompt_tokens,
        "eval_count": eval_tokens,
    }


# ------------------------------------------------------------------ routing


def test_prefix_routes_to_ollama_and_nothing_else_does():
    llm = FakeLLM(settings())
    assert llm.provider_of("ollama/gpt-oss:120b-cloud") == "ollama"
    # the collision the explicit prefix exists to prevent: Ollama serves models whose bare names
    # belong to other providers in this codebase
    assert llm.provider_of("qwen3.5:27b") == "dashscope"
    assert llm.provider_of("gemini-3.5-flash") == "gemini"
    assert llm.provider_of("global.anthropic.claude-haiku-4-5-20251001-v1:0") == "bedrock"


def test_ollama_cannot_run_the_walk():
    llm = FakeLLM(settings())
    assert llm.supports_tools("ollama/qwen3.5:27b") is False
    assert llm.supports_tools("gemini-3.5-flash") is True


def test_menu_normalises_a_comma_separated_env_var():
    s = settings(LIBKB_OLLAMA_MODELS="gpt-oss:120b-cloud, ollama/qwen3.5:27b")
    # the missing prefix is added: an unprefixed menu entry would be routed to Gemini
    assert s.ollama_models == ("ollama/gpt-oss:120b-cloud", "ollama/qwen3.5:27b")
    assert s.model_menu()[-2:] == ("ollama/gpt-oss:120b-cloud", "ollama/qwen3.5:27b")
    assert settings().model_menu() == settings().selectable_models  # empty by default


# ------------------------------------------------------------------ the request we send


def test_generate_strips_the_prefix_and_sends_the_native_shape():
    llm = FakeLLM(settings(), replies=[chat_reply("hello")])
    result = llm.generate("hi", model="ollama/gpt-oss:120b-cloud", system="be brief")

    path, payload = llm.posts[0]
    assert path == "/api/chat"
    assert payload["model"] == "gpt-oss:120b-cloud"  # our routing token never reaches Ollama
    assert payload["stream"] is False
    assert payload["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
    ]
    assert payload["think"] is False  # reasoning tokens are cost we do not ask for by default
    assert result.text == "hello"
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7
    assert llm.input_by_model == {"ollama/gpt-oss:120b-cloud": 11}


def test_a_json_schema_is_sent_as_format_so_the_server_enforces_it():
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    llm = FakeLLM(settings(), replies=[chat_reply('{"ok": true}')])
    assert llm.generate_json("q", schema=schema, model="ollama/qwen3.5:27b") == {"ok": True}
    assert llm.posts[0][1]["format"] == schema


def test_turns_become_ollama_roles():
    llm = FakeLLM(settings(), replies=[chat_reply("ok")])
    llm.generate(
        [Turn(role="user", text="a"), Turn(role="model", text="b"), Turn(role="user", text="c")],
        model="ollama/qwen3.5:27b",
    )
    assert [m["role"] for m in llm.posts[0][1]["messages"]] == ["user", "assistant", "user"]


def test_think_setting_is_honoured_and_omittable():
    assert _ollama_think("false") is False
    assert _ollama_think("high") == "high"
    assert _ollama_think("") is None
    llm = FakeLLM(settings(LIBKB_OLLAMA_THINK=""), replies=[chat_reply("ok")])
    llm.generate("hi", model="ollama/qwen3.5:27b")
    assert "think" not in llm.posts[0][1]  # empty ⇒ leave the model's own default alone


# ------------------------------------------------------------------ failing closed


def test_an_empty_message_raises_instead_of_returning_an_empty_answer():
    """P6's rule at the transport layer: a call that produced nothing must LOOK like a failure.
    `answer_query_safe` turns an LLMError into an honest NOT_FOUND; an empty string would sail on
    and be composed into an answer."""
    llm = FakeLLM(settings(), replies=[chat_reply("   ")])
    with pytest.raises(LLMError, match="empty message"):
        llm.generate("hi", model="ollama/qwen3.5:27b")


def test_tool_calling_is_refused_loudly():
    from libkb.llm.client import ToolSpec

    llm = FakeLLM(settings())
    spec = ToolSpec(name="open_shelf", description="", parameters={"type": "object"})
    with pytest.raises(LLMError, match="Gemini-only"):
        llm.generate("hi", model="ollama/qwen3.5:27b", tools=[spec])
    assert llm.posts == []  # refused before any network call


def test_a_400_about_think_drops_the_field_and_succeeds():
    """A model without a reasoning mode rejects `think`. That is a property of the model, not an
    error in the request we meant to make — so the field goes and the call proceeds."""
    request = httpx.Request("POST", "http://localhost:11434/api/chat")
    response = httpx.Response(400, text='{"error":"model does not support thinking"}')
    error = httpx.HTTPStatusError("400", request=request, response=response)
    llm = FakeLLM(settings(), replies=[error, chat_reply("done")])
    assert llm.generate("hi", model="ollama/gemma4:26b").text == "done"
    assert "think" in llm.posts[0][1] and "think" not in llm.posts[1][1]


def test_a_dead_daemon_becomes_an_LLMError_not_a_raw_httpx_error():
    """Transport errors that escape as themselves kill a run: `answer_query_safe` catches LLMError,
    and an unwrapped httpx error once ended a paid 301-case eval (SCORECARD §7.6)."""
    request = httpx.Request("POST", "http://localhost:11434/api/chat")
    boom = httpx.ConnectError("connection refused", request=request)
    llm = FakeLLM(settings(), replies=[boom] * 8)
    with pytest.raises(LLMError, match="Ollama call failed"):
        llm.generate("hi", model="ollama/qwen3.5:27b", max_retries=1)


# ------------------------------------------------------------------ embeddings


def test_embed_batches_and_normalises():
    vectors = [[3.0, 4.0], [0.0, 5.0]]
    llm = FakeLLM(settings(), replies=[{"embeddings": vectors}])
    out = llm.embed(["a", "b"], model="ollama/embeddinggemma:300m")
    assert llm.posts[0][0] == "/api/embed"
    assert llm.posts[0][1] == {"model": "embeddinggemma:300m", "input": ["a", "b"]}
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0)  # L2-normalised, as every caller assumes


def test_the_query_prefix_applies_to_queries_only():
    llm = FakeLLM(
        settings(LIBKB_OLLAMA_EMBED_QUERY_PREFIX="query: "),
        replies=[{"embeddings": [[1.0, 0.0]]}, {"embeddings": [[1.0, 0.0]]}],
    )
    llm.embed(["what is GMROI"], task="RETRIEVAL_QUERY", model="ollama/bge-m3")
    llm.embed(["a page body"], task="RETRIEVAL_DOCUMENT", model="ollama/bge-m3")
    assert llm.posts[0][1]["input"] == ["query: what is GMROI"]
    assert llm.posts[1][1]["input"] == ["a page body"]


def test_a_short_embedding_batch_is_loud():
    """Silently accepting fewer vectors than inputs would shift every row after the gap onto the
    wrong page — an unfalsifiable corruption of the catalog."""
    llm = FakeLLM(settings(), replies=[{"embeddings": [[1.0, 0.0]]}])
    with pytest.raises(LLMError, match="returned 1 vectors for 2"):
        llm.embed(["a", "b"], model="ollama/bge-m3")
