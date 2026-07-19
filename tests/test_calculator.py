"""Phase C.2 (D-061): the calculator tool + route, cost-gated by the router.

Two things matter here: `safe_eval` runs NO code (an injected expression can't execute), and the
route DEFERS to the library (returns None) when a message is not actually a calculation — so a
mis-route never fabricates.
"""

from __future__ import annotations

import pytest

from libkb import seed
from libkb.agent.orchestrator import answer_query
from libkb.agent.roles.registry import get_registry
from libkb.agent.roles.routes import RouteContext, decide_route, routes_from_registry
from libkb.config import get_settings
from libkb.library.store import LibraryStore
from libkb.tools.calculator import CalculatorRoute, safe_eval


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


class CalcFakeLLM:
    def __init__(self, route="calculator", expression="0.15 * 240", explain="15% of 240"):
        self.route, self.expression, self.explain = route, expression, explain

    def load_prompt(self, name, **kw):
        return f"[{name}]"

    def generate_json(self, prompt, *, schema=None, **kw):
        props = (schema or {}).get("properties", {})
        if "route" in props:
            return {"route": self.route}
        if "expression" in props:
            return {"expression": self.expression, "explain": self.explain}
        return {}

    def generate(self, *a, **k):
        raise AssertionError("a compute route must never start a walk")


def test_safe_eval_computes():
    assert safe_eval("0.15 * 240") == 36
    assert safe_eval("2 ** 10") == 1024
    assert safe_eval("(3 + 4) * 5") == 35
    assert safe_eval("6 * 7") == 42


def test_safe_eval_runs_no_code():
    for danger in ["__import__('os')", "a + b", "open('x')", "1 .__class__"]:
        with pytest.raises((ValueError, SyntaxError)):
            safe_eval(danger)


def test_calculator_tool_dispatches_through_the_registry():
    out = get_registry().dispatch("tool:calculator", {"expression": "3 * 4"})
    assert out == {"result": 12}


def test_calculator_route_answers_a_computation():
    answer, nav = CalculatorRoute().handle(
        RouteContext(
            query="what is 15% of 240?", store=None, llm=CalcFakeLLM(), settings=get_settings()
        )
    )
    assert answer.status == "answered"
    assert "36" in answer.text
    assert nav.reason == "calculator"


def test_calculator_route_defers_to_library_when_not_a_calculation():
    # empty expression from the extractor => None => the orchestrator falls back to the library
    out = CalculatorRoute().handle(
        RouteContext(
            query="who founded Rome?",
            store=None,
            llm=CalcFakeLLM(expression=""),
            settings=get_settings(),
        )
    )
    assert out is None


def test_calculator_is_a_registered_route():
    routes = routes_from_registry(get_registry())
    assert "calculator" in routes
    assert (
        decide_route("what is 15% of 240?", CalcFakeLLM(route="calculator"), get_settings(), routes)
        == "calculator"
    )


def test_orchestrator_routes_math_to_the_calculator(store):
    settings = get_settings().model_copy(update={"enable_router": True})
    result = answer_query(
        "what is 15% of 240?", store=store, llm=CalcFakeLLM(), settings=settings, use_catalog=False
    )
    assert result.nav.reason == "calculator"
    assert "36" in result.answer.text
