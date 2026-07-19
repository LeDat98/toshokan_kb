"""Front-door routing (D-061): the orchestrator decides social-vs-cascade-vs-tool, registry-driven.

The load-bearing test is `test_new_route_appears_in_the_menu_without_editing_the_decision`: a brand-
new route shows up in the menu and is selectable with NO change to `decide_route` or orchestrator —
the same "register, don't edit" guarantee as Phases B/C, now for routing. LLM-free via a fake.
"""

from __future__ import annotations

import pytest

from libkb import seed
from libkb.agent.roles.base import AgentCard
from libkb.agent.roles.registry import AgentRegistry, get_registry
from libkb.agent.roles.routes import (
    ConciergeAgent,
    RouteContext,
    decide_route,
    routes_from_registry,
)
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


class RouteFakeLLM:
    """Returns a route for the route_query schema and an answer for the concierge schema; can raise
    to simulate a model/network failure."""

    def __init__(self, route=None, answer="Hi!", raise_on_json=False):
        self.route, self.answer, self.raise_on_json = route, answer, raise_on_json

    def load_prompt(self, name, **kw):
        return f"[{name}]"

    def generate_json(self, prompt, *, schema=None, **kw):
        if self.raise_on_json:
            raise RuntimeError("boom")
        props = (schema or {}).get("properties", {})
        return {"route": self.route} if "route" in props else {"answer": self.answer}


def test_default_registry_exposes_the_two_routes():
    routes = routes_from_registry(get_registry())
    assert "answer_directly" in routes
    assert "search_library" in routes
    assert routes["search_library"].route_when  # carries a when-to-use line


def test_greeting_routes_directly_with_no_model_call():
    # Layer 0 is code-only: a RAISING llm proves no model call happens for a plain greeting.
    routes = routes_from_registry(get_registry())
    llm = RouteFakeLLM(raise_on_json=True)
    assert decide_route("hello", llm, get_settings(), routes) == "answer_directly"
    assert decide_route("cảm ơn", llm, get_settings(), routes) == "answer_directly"


def test_knowledge_query_uses_the_model_choice():
    routes = routes_from_registry(get_registry())
    got = decide_route(
        "what is reranking?", RouteFakeLLM(route="search_library"), get_settings(), routes
    )
    assert got == "search_library"


def test_unknown_route_and_errors_fail_safe_to_search_library():
    routes = routes_from_registry(get_registry())
    assert (
        decide_route("q", RouteFakeLLM(route="nonsense"), get_settings(), routes)
        == "search_library"
    )
    assert (
        decide_route("q", RouteFakeLLM(raise_on_json=True), get_settings(), routes)
        == "search_library"
    )


def test_new_route_appears_in_the_menu_without_editing_the_decision():
    reg = AgentRegistry()

    class WeatherRoute:
        card = AgentCard(
            id="weather",
            name="Weather",
            description="Live weather.",
            route_when="questions about today's weather",
        )

    reg.register(WeatherRoute())
    routes = routes_from_registry(reg)
    assert "weather" in routes
    # selectable through the SAME decide_route, unchanged
    assert (
        decide_route("will it rain?", RouteFakeLLM(route="weather"), get_settings(), routes)
        == "weather"
    )


def test_concierge_answers_directly_without_retrieval(store):
    answer, nav = ConciergeAgent().handle(
        RouteContext(
            query="who are you?",
            store=store,
            llm=RouteFakeLLM(answer="I'm the librarian; ask me and I'll search the library."),
            settings=get_settings(),
        )
    )
    assert answer.status == "answered"
    assert "librarian" in answer.text.lower()
    assert nav.reason == "concierge"
    assert not answer.citations  # no retrieval, so nothing cited
