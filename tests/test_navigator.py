"""Navigator loop tests with a scripted fake LLM — no real API calls."""

import pytest

from libkb import seed
from libkb.agent.navigator import navigate
from libkb.config import get_settings
from libkb.library.store import LibraryStore
from libkb.llm.client import LLMResult, ToolCall


class FakeLLM:
    """Returns a pre-scripted tool call per generate() invocation."""

    def __init__(self, script: list[tuple[str, dict]]):
        self._script = list(script)
        self.calls = 0

    def load_prompt(self, name, **kw):
        return f"[prompt:{name}]"

    def generate(self, contents, **kwargs):
        if self.calls < len(self._script):
            name, args = self._script[self.calls]
            self.calls += 1
            return LLMResult(text=None, tool_calls=[ToolCall(name=name, args=args)])
        self.calls += 1
        return LLMResult(text="", tool_calls=[ToolCall(name="not_found", args={"reason": "end"})])


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store(tmp_path):
    s = LibraryStore(tmp_path / "library")
    s.init_library()
    seed.apply(s)
    return s


def test_scripted_walk_finds_reranking(store):
    fake = FakeLLM(
        [
            ("browse", {"target": "AI"}),
            ("browse", {"target": "RAG"}),
            ("open_book", {"title": "Advanced RAG Techniques"}),
            ("read_page", {"title": "Reranking & Cross-encoders"}),
            ("found", {"note": "on the reranking page"}),
        ]
    )
    events = []
    result = navigate("What is reranking?", store=store, llm=fake, event_cb=events.append)
    assert result.status == "FOUND"
    assert len(result.pages) == 1
    assert "cross-encoder" in result.pages[0].markdown.lower()
    assert [e.action for e in events][-1] == "found"
    assert result.backtracks == 0


def test_scripted_walk_with_backtrack(store):
    fake = FakeLLM(
        [
            ("browse", {"target": "AI"}),
            ("browse", {"target": "LLM"}),  # wrong shelf
            ("go_back", {"reason": "reranking is a RAG topic, not LLM"}),
            ("browse", {"target": "RAG"}),
            ("open_book", {"title": "Advanced RAG Techniques"}),
            ("read_page", {"title": "Reranking & Cross-encoders"}),
            ("found", {"note": "found it"}),
        ]
    )
    result = navigate("reranking?", store=store, llm=fake)
    assert result.status == "FOUND"
    assert result.backtracks == 1


def test_scripted_not_found(store):
    fake = FakeLLM(
        [
            ("browse", {"target": "AI"}),
            ("not_found", {"reason": "no quantum error correction here", "closest": ["AI ▸ ML"]}),
        ]
    )
    result = navigate("quantum error correction?", store=store, llm=fake)
    assert result.status == "NOT_FOUND"
    assert result.pages == []
    assert result.closest == ["AI ▸ ML"]


def test_prose_without_tool_call_is_nudged_then_concludes(store):
    class ProseLLM(FakeLLM):
        def generate(self, contents, **kwargs):
            self.calls += 1
            return LLMResult(text="I think the answer is 42.", tool_calls=[])

    result = navigate("anything?", store=store, llm=ProseLLM([]))
    assert result.status == "NOT_FOUND"  # never concluded via a tool
