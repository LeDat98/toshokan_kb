"""Catalog-navigator + Clarify routes (D-061 skills): both plug into the routing seam, both DEFER to
the library on a mis-route (return None), and the navigator's answer is read from the store (never
invented). LLM-free via a fake."""

from __future__ import annotations

import pytest

from libkb import seed
from libkb.agent.roles.catalog_nav import CatalogNavigatorRoute
from libkb.agent.roles.clarify import ClarifyRoute
from libkb.agent.roles.registry import get_registry
from libkb.agent.roles.routes import RouteContext, decide_route, routes_from_registry
from libkb.config import get_settings
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


class SkillFakeLLM:
    def __init__(
        self, list_="domains", under="", ambiguous=False, question="Which one?", route=None
    ):
        self.list_, self.under = list_, under
        self.ambiguous, self.question, self.route = ambiguous, question, route

    def load_prompt(self, name, **kw):
        return f"[{name}]"

    def generate_json(self, prompt, *, schema=None, **kw):
        props = (schema or {}).get("properties", {})
        if "route" in props:
            return {"route": self.route}
        if "list" in props:
            return {"list": self.list_, "under": self.under}
        if "ambiguous" in props:
            return {"ambiguous": self.ambiguous, "question": self.question}
        return {}


def _ctx(query, store, llm):
    return RouteContext(query=query, store=store, llm=llm, settings=get_settings())


def test_catalog_lists_domains_from_the_store(store):
    answer, nav = CatalogNavigatorRoute().handle(
        _ctx("what domains do you have?", store, SkillFakeLLM(list_="domains"))
    )
    assert answer.status == "answered"
    assert "AI" in answer.text
    assert nav.reason == "catalog"


def test_catalog_lists_shelves_under_a_domain(store):
    answer, _ = CatalogNavigatorRoute().handle(
        _ctx("what shelves are in AI?", store, SkillFakeLLM(list_="shelves", under="AI"))
    )
    assert "RAG" in answer.text  # AI ▸ {RAG, LLM, CV}


def test_catalog_unknown_container_is_honest(store):
    answer, _ = CatalogNavigatorRoute().handle(
        _ctx("books in Zzz?", store, SkillFakeLLM(list_="books", under="Zzz"))
    )
    assert "don't have" in answer.text.lower()
    assert "AI" in answer.text  # tells them what does exist


def test_catalog_defers_when_not_structural(store):
    out = CatalogNavigatorRoute().handle(
        _ctx("what is reranking?", store, SkillFakeLLM(list_="none"))
    )
    assert out is None


def test_clarify_asks_one_question(store):
    answer, nav = ClarifyRoute().handle(
        _ctx("compare them", store, SkillFakeLLM(ambiguous=True, question="Compare which two?"))
    )
    assert answer.status == "answered"
    assert answer.text == "Compare which two?"
    assert nav.reason == "clarify"


def test_clarify_defers_when_answerable(store):
    out = ClarifyRoute().handle(_ctx("what is reranking?", store, SkillFakeLLM(ambiguous=False)))
    assert out is None


def test_both_skills_are_registered_routes():
    routes = routes_from_registry(get_registry())
    assert "catalog" in routes
    assert "clarify" in routes


def test_router_can_select_the_skills(store):
    routes = routes_from_registry(get_registry())
    assert (
        decide_route("list your domains", SkillFakeLLM(route="catalog"), get_settings(), routes)
        == "catalog"
    )
    assert (
        decide_route("tell me about it", SkillFakeLLM(route="clarify"), get_settings(), routes)
        == "clarify"
    )
