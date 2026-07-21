"""The cross-document synthesizer (D-061): a map-reduce over a WIDE scan for aggregative questions.

Covered here, all LLM-free via fakes:
- the map-reduce answers from FINDINGS (each read from a real page) and cites the contributors;
- a page that contributes nothing is DROPPED (map returns relevant=false);
- an empty harvest is an honest NOT_FOUND (P6), never a synthesised guess;
- the route DEFERS (returns None) on a single-fact question, so a mis-route falls to the cascade;
- the falsifiable seam check: the route registers and is SELECTABLE with no orchestrator edit.
"""

from __future__ import annotations

import pytest

from libkb import seed
from libkb.agent import synthesizer as synth
from libkb.agent.roles.catalog_nav import _descendants
from libkb.agent.roles.registry import get_registry
from libkb.agent.roles.routes import RouteContext, decide_route, routes_from_registry
from libkb.agent.roles.synthesizer import SynthesizerRoute
from libkb.catalog.store import Hit
from libkb.config import Settings, get_settings
from libkb.library.models import ROOT_ID
from libkb.library.store import LibraryStore


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


def _page_ids(store, n):
    return [node.id for node in _descendants(store, ROOT_ID, "page")][:n]


def _sequential():
    """Settings with a single map worker, so parallel_map runs in input order and the fake's
    findings line up with the pages deterministically."""
    return Settings(synth_concurrency=1)


class SynthFakeLLM:
    """Dispatches by the schema it is handed: detect / map / reduce. Map findings are consumed in
    order (safe because tests force synth_concurrency=1)."""

    def __init__(
        self, findings=None, reduce_answer="", aggregative=True, scope="", sufficient=True
    ):
        self._findings = list(findings or [])
        self._i = 0
        self.reduce_answer = reduce_answer
        self.aggregative = aggregative
        self.scope = scope
        self.sufficient = sufficient

    def embed(self, texts, task=None):
        return [[0.0, 0.0, 0.0] for _ in texts]

    def load_prompt(self, name, **kw):
        return f"[{name}]"

    def generate_json(self, prompt, *, schema=None, **kw):
        props = (schema or {}).get("properties", {})
        if "aggregative" in props:
            return {"aggregative": self.aggregative, "scope": self.scope}
        if "relevant" in props:
            finding = self._findings[self._i] if self._i < len(self._findings) else ""
            self._i += 1
            return {"relevant": bool(finding), "finding": finding}
        if "answer" in props:  # reduce
            return {
                "answer": self.reduce_answer,
                "confidence": "high",
                "sufficient": self.sufficient,
                "thought": "surveyed the shelves",
            }
        return {}


def _fake_hits(store, ids):
    return [Hit(page_id=i, book_id="", path="", text="", lang="", score=0.9) for i in ids]


def _ctx(query, store, llm, settings=None):
    return RouteContext(query=query, store=store, llm=llm, settings=settings or get_settings())


# ── the map-reduce engine ──────────────────────────────────────────────────────────────────────


def test_synthesize_reduces_findings_into_a_cited_answer(store, monkeypatch):
    ids = _page_ids(store, 3)
    monkeypatch.setattr(synth, "lookup", lambda *a, **k: _fake_hits(store, ids))
    llm = SynthFakeLLM(
        findings=["A uses chunking", "B uses reranking", "C uses HNSW"],
        reduce_answer="Across the pages, the common theme is retrieval engineering.",
    )
    result = synth.synthesize(
        "what techniques appear across the library?",
        store=store,
        catalog=object(),
        llm=llm,
        settings=_sequential(),
    )
    assert result.answer.status == "answered"
    assert "retrieval engineering" in result.answer.text
    assert len(result.findings) == 3
    # every contributing page is cited, and the trace carries the real pages (metadata, not re-sent)
    assert len(result.answer.citations) == 3
    assert len(result.nav.pages) == 3
    assert result.nav.reason == "synthesize"


def test_synthesize_drops_pages_that_contribute_nothing(store, monkeypatch):
    ids = _page_ids(store, 3)
    monkeypatch.setattr(synth, "lookup", lambda *a, **k: _fake_hits(store, ids))
    # the middle page returns relevant=false (empty finding) → dropped from the synthesis
    llm = SynthFakeLLM(findings=["A matters", "", "C matters"], reduce_answer="Two sources agree.")
    result = synth.synthesize(
        "trends?", store=store, catalog=object(), llm=llm, settings=_sequential()
    )
    assert result.answer.status == "answered"
    assert len(result.findings) == 2
    assert len(result.answer.citations) == 2


def test_synthesize_is_honest_when_nothing_contributes(store, monkeypatch):
    ids = _page_ids(store, 3)
    monkeypatch.setattr(synth, "lookup", lambda *a, **k: _fake_hits(store, ids))
    llm = SynthFakeLLM(findings=["", "", ""], reduce_answer="(should never be reached)")
    result = synth.synthesize(
        "trends?", store=store, catalog=object(), llm=llm, settings=_sequential()
    )
    assert result.answer.status == "not_found"  # scanned wide, nothing to synthesise → NOT_FOUND
    assert result.nav.status == "NOT_FOUND"


def test_synthesize_not_found_when_scan_is_empty(store, monkeypatch):
    monkeypatch.setattr(synth, "lookup", lambda *a, **k: [])
    llm = SynthFakeLLM(findings=[], reduce_answer="x")
    result = synth.synthesize(
        "trends?", store=store, catalog=object(), llm=llm, settings=_sequential()
    )
    assert result.answer.status == "not_found"


def test_synthesize_abstains_when_reducer_says_insufficient(store, monkeypatch):
    ids = _page_ids(store, 2)
    monkeypatch.setattr(synth, "lookup", lambda *a, **k: _fake_hits(store, ids))
    llm = SynthFakeLLM(findings=["A", "B"], reduce_answer="", sufficient=False)
    result = synth.synthesize(
        "trends?", store=store, catalog=object(), llm=llm, settings=_sequential()
    )
    assert result.answer.status == "not_found"


# ── the route ───────────────────────────────────────────────────────────────────────────────────


def test_route_defers_on_a_single_fact_question(store):
    # aggregative=false → None BEFORE any catalog is opened, so the cascade handles it
    out = SynthesizerRoute().handle(
        _ctx("what is reranking?", store, SynthFakeLLM(aggregative=False))
    )
    assert out is None


def test_route_defers_when_no_catalog_on_disk(store, tmp_path):
    # aggregative=true, but db_path points at no catalog → defer to the walk rather than crash.
    # (Settings.db_path is isolated to tmp so the test never touches the real project catalog.)
    settings = Settings(db_path=tmp_path / "nonexistent" / "catalog.db")
    out = SynthesizerRoute().handle(
        _ctx(
            "what are the trends across the whole library?",
            store,
            SynthFakeLLM(aggregative=True),
            settings=settings,
        )
    )
    assert out is None


# ── the seam: registered + selectable with NO orchestrator edit ──────────────────────────────────


def test_synthesizer_is_a_registered_route():
    routes = routes_from_registry(get_registry())
    assert "synthesize" in routes


def test_router_can_select_the_synthesizer(store):
    class RouteFake:
        def load_prompt(self, name, **kw):
            return f"[{name}]"

        def generate_json(self, prompt, *, schema=None, **kw):
            return {"route": "synthesize"}

    routes = routes_from_registry(get_registry())
    assert (
        decide_route("summarise the trends across every book", RouteFake(), get_settings(), routes)
        == "synthesize"
    )
