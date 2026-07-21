"""History-aware query rewriting: a follow-up becomes a standalone query; everything else is left
alone. LLM-free. Conservative + fail-open — a self-contained question and any error both return the
original query, so multi-turn never costs the single-shot cascade an answer.
"""

from __future__ import annotations

import pytest

from libkb.agent.contextualize import contextualize
from libkb.config import get_settings


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeLLM:
    def __init__(self, followup=False, standalone="", boom=False):
        self.followup, self.standalone, self.boom = followup, standalone, boom

    def load_prompt(self, name, **kw):
        return f"[{name}]"

    def generate_json(self, prompt, *, schema=None, **kw):
        if self.boom:
            raise RuntimeError("model down")
        return {"followup": self.followup, "standalone": self.standalone}


def _hist():
    return [
        {"role": "user", "text": "what is reranking?"},
        {"role": "assistant", "text": "Reranking reorders candidates."},
    ]


def test_no_history_is_a_free_no_op():
    r = contextualize("hello", [], FakeLLM(), get_settings())
    assert r.rewritten is False and r.query == "hello"


def test_a_self_contained_question_is_unchanged():
    r = contextualize("what is HNSW?", _hist(), FakeLLM(followup=False), get_settings())
    assert r.rewritten is False and r.query == "what is HNSW?"


def test_a_followup_is_rewritten_to_standalone():
    r = contextualize(
        "tell me more about it",
        _hist(),
        FakeLLM(followup=True, standalone="tell me more about reranking"),
        get_settings(),
    )
    assert r.rewritten is True
    assert r.query == "tell me more about reranking"
    assert r.original == "tell me more about it"
    assert r.thought  # a first-person line for the timeline


def test_empty_standalone_falls_back_to_the_original():
    llm = FakeLLM(followup=True, standalone="")
    r = contextualize("tell me more", _hist(), llm, get_settings())
    assert r.rewritten is False and r.query == "tell me more"


def test_error_fails_open():
    r = contextualize("tell me more", _hist(), FakeLLM(boom=True), get_settings())
    assert r.rewritten is False and r.query == "tell me more"


def test_answer_query_rewrites_a_followup_before_retrieval(monkeypatch, tmp_path):
    """The wiring: with history present, the orchestrator hands RETRIEVAL the standalone query, and
    narrates the rewrite. navigate is stubbed so the test stays LLM-free and catalog-free."""
    from libkb.agent import orchestrator
    from libkb.agent.navigator import NavResult
    from libkb.library.store import LibraryStore

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("LIBKB_LOG_TRAJECTORIES", "false")  # don't touch the real trajectory db
    get_settings.cache_clear()

    seen: dict = {}

    def fake_navigate(query, **kw):
        seen["query"] = query
        return NavResult(status="NOT_FOUND", reason="stub")

    monkeypatch.setattr(orchestrator, "navigate", fake_navigate)

    store = LibraryStore(tmp_path / "library")
    store.init_library()
    events = []
    orchestrator.answer_query(
        "tell me more about it",
        store=store,
        llm=FakeLLM(followup=True, standalone="tell me more about reranking"),
        use_catalog=False,
        event_cb=events.append,
        history=[{"role": "user", "text": "what is reranking?"}],
    )

    assert seen["query"] == "tell me more about reranking"  # retrieval saw the STANDALONE query
    assert any(e.action == "thought" and e.detail == "context" for e in events)
    get_settings.cache_clear()
