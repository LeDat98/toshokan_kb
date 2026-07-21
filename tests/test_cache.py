"""The semantic answer cache: cosine lookup, the honesty rules on write, and an end-to-end hit
through the orchestrator. LLM-free via fake vectors.

The rules that keep it trustworthy are the point: never cache a NOT_FOUND, only grounded + confident
answers, and a hit must clear a conservative threshold. A curated (edited) answer is sticky.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from libkb import seed
from libkb.agent.answerer import Answer, Citation
from libkb.agent.orchestrator import answer_query
from libkb.cache.lookup import cache_lookup, cache_put
from libkb.cache.store import AnswerCache
from libkb.config import get_settings
from libkb.library.store import LibraryStore


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _put(cache, query, vec, answer="ans", cites=True, conf="high"):
    return cache.put(
        query,
        vec,
        answer,
        [{"path": "AI ▸ RAG", "page_id": "p1"}] if cites else [],
        conf,
        ["p1"],
    )


# ── the store: cosine search + CRUD ──────────────────────────────────────────────────────────


def test_put_and_search_hit(tmp_path):
    c = AnswerCache(tmp_path / "catalog.db")
    _put(c, "what is reranking?", [1.0, 0.0, 0.0, 0.0], answer="Reranking reorders results.")
    hit = c.search([1.0, 0.0, 0.0, 0.0], threshold=0.93)  # identical direction → cosine 1.0
    assert hit is not None and "Reranking" in hit.entry.answer
    assert hit.score > 0.99
    c.close()


def test_search_miss_below_threshold(tmp_path):
    c = AnswerCache(tmp_path / "catalog.db")
    _put(c, "q", [1.0, 0.0, 0.0, 0.0])
    assert c.search([0.0, 1.0, 0.0, 0.0], threshold=0.93) is None  # orthogonal → cosine 0
    c.close()


def test_disabled_entry_is_not_returned(tmp_path):
    c = AnswerCache(tmp_path / "catalog.db")
    eid = _put(c, "q", [1.0, 0.0, 0.0, 0.0])
    c.set_entry_enabled(eid, False)
    assert c.search([1.0, 0.0, 0.0, 0.0], threshold=0.93) is None
    c.close()


def test_global_toggle_persists(tmp_path):
    c = AnswerCache(tmp_path / "catalog.db")
    assert c.is_enabled() is True  # default ON
    c.set_enabled(False)
    assert c.is_enabled() is False
    c.close()
    assert AnswerCache(tmp_path / "catalog.db").is_enabled() is False  # survives reopen


def test_update_answer_marks_curated(tmp_path):
    c = AnswerCache(tmp_path / "catalog.db")
    eid = _put(c, "q", [1.0, 0.0, 0.0, 0.0])
    assert c.get(eid).curated is False
    assert c.update_answer(eid, "a better, human-approved answer") is True
    e = c.get(eid)
    assert e.curated is True and "human-approved" in e.answer
    c.close()


def test_invalidate_drops_noncurated_keeps_curated(tmp_path):
    c = AnswerCache(tmp_path / "catalog.db")
    auto = _put(c, "auto", [1.0, 0.0, 0.0, 0.0])
    cur = _put(c, "curated", [0.0, 1.0, 0.0, 0.0])
    c.update_answer(cur, "human-owned")  # marks curated
    dropped = c.invalidate_pages({"p1"})  # both cite p1
    assert dropped == 1  # only the non-curated one
    assert c.get(auto) is None and c.get(cur) is not None
    c.close()


def test_list_orders_by_hits(tmp_path):
    c = AnswerCache(tmp_path / "catalog.db")
    a = _put(c, "a", [1.0, 0.0, 0.0, 0.0])
    b = _put(c, "b", [0.0, 1.0, 0.0, 0.0])
    for _ in range(3):
        c.record_hit(b)
    assert [e.id for e in c.list()][0] == b  # most-hit first
    assert {e.id for e in c.list()} == {a, b}
    c.close()


# ── the honesty rules on write ──────────────────────────────────────────────────────────────────


def _result(status="answered", conf="high", cites=True):
    ans = Answer(
        text="the answer",
        status=status,
        confidence=conf,
        citations=[Citation(path="AI ▸ RAG", page_id="p1")] if cites else [],
    )
    return SimpleNamespace(answer=ans, nav=SimpleNamespace(pages=[]))


class VecLLM:
    def __init__(self, vec):
        self.vec = vec

    def embed(self, texts, task=None):
        return [self.vec]


def test_cache_put_refuses_not_found(tmp_path):
    c = AnswerCache(tmp_path / "catalog.db")
    cache_put(c, "q", [1.0, 0.0], _result(status="not_found"), get_settings())
    assert c.count() == 0  # a gap must stay retriable
    c.close()


def test_cache_put_refuses_without_citations(tmp_path):
    c = AnswerCache(tmp_path / "catalog.db")
    cache_put(c, "q", [1.0, 0.0], _result(cites=False), get_settings())
    assert c.count() == 0  # only grounded answers are cached
    c.close()


def test_cache_put_refuses_below_confidence(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBKB_ANSWER_CACHE_MIN_CONFIDENCE", "high")
    get_settings.cache_clear()
    c = AnswerCache(tmp_path / "catalog.db")
    cache_put(c, "q", [1.0, 0.0], _result(conf="low"), get_settings())
    assert c.count() == 0
    c.close()


def test_cache_put_stores_a_grounded_answer(tmp_path):
    c = AnswerCache(tmp_path / "catalog.db")
    cache_put(c, "q", [1.0, 0.0], _result(), get_settings())
    assert c.count() == 1
    c.close()


def test_cache_lookup_returns_vec_even_on_miss(tmp_path):
    c = AnswerCache(tmp_path / "catalog.db")  # empty → always a miss
    hit, vec = cache_lookup(c, "q", VecLLM([1.0, 0.0, 0.0, 0.0]), get_settings())
    assert (
        hit is None and vec is not None
    )  # vec returned so the caller can WRITE without re-embedding
    c.close()


def test_cache_lookup_off_when_globally_disabled(tmp_path):
    c = AnswerCache(tmp_path / "catalog.db")
    _put(c, "q", [1.0, 0.0, 0.0, 0.0])
    c.set_enabled(False)
    hit, vec = cache_lookup(c, "q", VecLLM([1.0, 0.0, 0.0, 0.0]), get_settings())
    assert hit is None and vec is None  # disabled → no work at all
    c.close()


# ── end-to-end through the orchestrator ─────────────────────────────────────────────────────────


def test_orchestrator_serves_a_cached_answer(tmp_path, monkeypatch):
    """A second, differently-worded question whose embedding matches a cached one is answered FROM
    the cache — reason='cache', zero retrieval/generation."""
    db = tmp_path / "catalog.db"
    monkeypatch.setenv("LIBKB_DB_PATH", str(db))
    get_settings.cache_clear()

    store = LibraryStore(tmp_path / "library")
    store.init_library()
    seed.apply(store)

    vec = [1.0, 0.0, 0.0, 0.0]
    c = AnswerCache(db)
    c.put(
        "what is reranking?",
        vec,
        "Reranking reorders the top-k candidates.",
        [{"path": "AI ▸ RAG ▸ p.12", "page_id": "p12"}],
        "high",
        ["p12"],
    )
    c.close()

    result = answer_query(
        "how does reranking work?",  # different words, same meaning (fake embed → same vec)
        store=store,
        llm=VecLLM(vec),
        settings=get_settings(),
    )
    assert result.nav.reason == "cache"
    assert "Reranking reorders" in result.answer.text
    assert result.answer.citations[0].path == "AI ▸ RAG ▸ p.12"
