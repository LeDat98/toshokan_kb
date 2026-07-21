"""Query decomposition for compound multi-hop questions. LLM-free via fakes.

Covered:
- each sub-question is retrieved SHARPLY (its own query), the union feeds ONE combine call, cited;
- pages shared across sub-questions are DEDUPED in the citations;
- an empty retrieval and an insufficient combine both yield an honest NOT_FOUND (P6);
- the route DEFERS (None) on a non-compound question and on a <2-subquestion split;
- the falsifiable seam: the route registers and is SELECTABLE with no orchestrator edit.
"""

from __future__ import annotations

import pytest

from libkb import seed
from libkb.agent import decompose as dec
from libkb.agent.roles.catalog_nav import _descendants
from libkb.agent.roles.decompose import DecomposeRoute
from libkb.agent.roles.routes import RouteContext, decide_route, routes_from_registry
from libkb.catalog.store import Hit
from libkb.config import get_settings
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


def _hit(pid):
    return Hit(page_id=pid, book_id="", path="", text="", lang="", score=0.9)


class DecFakeLLM:
    def __init__(self, combine_answer="ok", sufficient=True, compound=True, subs=None):
        self.combine_answer = combine_answer
        self.sufficient = sufficient
        self.compound = compound
        self.subs = subs if subs is not None else ["a", "b", "c"]

    def embed(self, texts, task=None):
        return [[0.0, 0.0, 0.0] for _ in texts]

    def load_prompt(self, name, **kw):
        return f"[{name}]"

    def generate_json(self, prompt, *, schema=None, **kw):
        props = (schema or {}).get("properties", {})
        if "compound" in props:  # split
            return {"compound": self.compound, "sub_questions": self.subs}
        if "answer" in props:  # combine
            return {
                "answer": self.combine_answer,
                "confidence": "high",
                "sufficient": self.sufficient,
                "thought": "combined the parts",
            }
        return {}


def _ctx(query, store, llm):
    return RouteContext(query=query, store=store, llm=llm, settings=get_settings())


# ── the engine ────────────────────────────────────────────────────────────────────────────────────


def test_decompose_retrieves_per_subquestion_and_combines(store, monkeypatch):
    ids = _page_ids(store, 3)
    subs = ["policy before X", "policy after X", "policy for international"]
    qmap = dict(zip(subs, ids, strict=True))
    # each sub-question gets its OWN sharp retrieval → a different page
    monkeypatch.setattr(
        dec, "lookup", lambda catalog, q, **kw: [_hit(qmap[q])] if q in qmap else []
    )

    llm = DecFakeLLM(combine_answer="Before it was A; after, B; international orders use C.")
    result = dec.decompose_answer(
        "compare before/after and which for international",
        subs,
        store=store,
        catalog=object(),
        llm=llm,
        settings=get_settings(),
    )
    assert result.answer.status == "answered"
    assert "international" in result.answer.text.lower()
    assert len(result.answer.citations) == 3  # union of the three distinct pages
    assert len(result.nav.pages) == 3
    assert result.nav.reason == "decompose"


def test_decompose_dedupes_pages_shared_across_subquestions(store, monkeypatch):
    ids = _page_ids(store, 1)
    # both sub-questions retrieve the SAME page → the union must collapse to one citation
    monkeypatch.setattr(dec, "lookup", lambda catalog, q, **kw: [_hit(ids[0])])
    result = dec.decompose_answer(
        "q",
        ["part one", "part two"],
        store=store,
        catalog=object(),
        llm=DecFakeLLM(),
        settings=get_settings(),
    )
    assert result.answer.status == "answered"
    assert len(result.answer.citations) == 1


def test_decompose_not_found_when_nothing_retrieved(store, monkeypatch):
    monkeypatch.setattr(dec, "lookup", lambda *a, **k: [])
    result = dec.decompose_answer(
        "q", ["a", "b"], store=store, catalog=object(), llm=DecFakeLLM(), settings=get_settings()
    )
    assert result.answer.status == "not_found"
    assert result.nav.status == "NOT_FOUND"


def test_decompose_abstains_when_combine_insufficient(store, monkeypatch):
    ids = _page_ids(store, 2)
    monkeypatch.setattr(dec, "lookup", lambda catalog, q, **kw: [_hit(ids[0])])
    llm = DecFakeLLM(combine_answer="", sufficient=False)
    result = dec.decompose_answer(
        "q", ["a", "b"], store=store, catalog=object(), llm=llm, settings=get_settings()
    )
    assert result.answer.status == "not_found"


# ── the route (defer paths only — the engine is tested directly, no real catalog) ────────────────


def test_route_defers_on_a_non_compound_question(store):
    out = DecomposeRoute().handle(_ctx("what is reranking?", store, DecFakeLLM(compound=False)))
    assert out is None


def test_route_defers_when_the_split_yields_under_two(store):
    out = DecomposeRoute().handle(
        _ctx("q", store, DecFakeLLM(compound=True, subs=["only one part"]))
    )
    assert out is None


# ── the seam: registered + selectable with NO orchestrator edit ──────────────────────────────────


def _fresh_registry(monkeypatch):
    """Rebuild the lazily-cached registry so a changed knob takes effect (restored on teardown)."""
    from libkb.agent.roles import registry as reg_mod

    monkeypatch.setattr(reg_mod, "_default", None)
    return reg_mod.get_registry()


def test_decompose_is_not_offered_to_the_router_by_default(monkeypatch):
    """MEASURED AND REFUTED (SCORECARD §3.2) — so the router must never be able to pick it."""
    assert "decompose" not in routes_from_registry(_fresh_registry(monkeypatch))


def test_decompose_can_be_re_enabled_to_reproduce_the_measurement(monkeypatch):
    monkeypatch.setenv("LIBKB_ENABLE_DECOMPOSE", "true")
    get_settings.cache_clear()
    assert "decompose" in routes_from_registry(_fresh_registry(monkeypatch))


def test_router_can_select_decompose_when_re_enabled(monkeypatch):
    monkeypatch.setenv("LIBKB_ENABLE_DECOMPOSE", "true")
    get_settings.cache_clear()

    class RouteFake:
        def load_prompt(self, name, **kw):
            return f"[{name}]"

        def generate_json(self, prompt, *, schema=None, **kw):
            return {"route": "decompose"}

    routes = routes_from_registry(_fresh_registry(monkeypatch))
    got = decide_route(
        "compare the policy before and after the change, and which applies to B",
        RouteFake(),
        get_settings(),
        routes,
    )
    assert got == "decompose"


def test_force_route_bypasses_the_classifier(monkeypatch):
    """The measurement knob: LIBKB_FORCE_ROUTE sends every query to one route without ever calling
    the lite classifier. Uses `synthesize` (registered by default) so it exercises the force
    mechanism itself, independent of decompose now being off."""
    from libkb.config import Settings

    class NeverCalled:
        def load_prompt(self, *a, **k):
            raise AssertionError("the classifier must be bypassed when force_route is set")

        def generate_json(self, *a, **k):
            raise AssertionError("the classifier must be bypassed when force_route is set")

    routes = routes_from_registry(_fresh_registry(monkeypatch))
    settings = Settings(force_route="synthesize")
    assert decide_route("anything at all", NeverCalled(), settings, routes) == "synthesize"
