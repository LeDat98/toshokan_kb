"""Phase B (D-061): agents as typed roles behind a registry, with A2A-shaped cards.

The load-bearing test is `test_new_agent_registers_and_dispatches_without_touching_orchestrator`: it
is the falsifiable check for the whole phase — a brand-new agent plugs in and runs with NO import
of, or edit to, the cascade/orchestrator. If that ever needs the orchestrator changed, the seam is
fake.
"""

from __future__ import annotations

import pytest

from libkb.agent.roles.base import AgentCard
from libkb.agent.roles.registry import AgentRegistry, get_registry


def test_default_registry_has_the_core_roles():
    reg = get_registry()
    for role_id in ("librarian", "answerer", "verifier"):
        assert reg.has(role_id)
    ids = {c.id for c in reg.cards()}
    assert {"librarian", "answerer", "verifier"} <= ids


def test_verifier_is_dispatchable_and_catches_an_invented_figure():
    reg = get_registry()
    bad = reg.dispatch("verifier", {"answer": "The rate is 42%.", "evidence": "The rate is low."})
    assert bad["ok"] is False
    assert "42%" in bad["invented"]

    good = reg.dispatch("verifier", {"answer": "The rate is low.", "evidence": "The rate is low."})
    assert good["ok"] is True
    assert good["invented"] == []


def test_pipeline_role_is_not_generically_dispatchable():
    # The Librarian operates on live objects (store/LLM), so it has no generic run() — dispatching
    # it generically is a programming error, and the registry says so rather than crash obscurely.
    reg = get_registry()
    with pytest.raises(TypeError):
        reg.dispatch("librarian", {})


def test_register_requires_a_card():
    reg = AgentRegistry()

    class NotAnAgent:
        pass

    with pytest.raises(TypeError):
        reg.register(NotAnAgent())


def test_new_agent_registers_and_dispatches_without_touching_orchestrator():
    # NOTE: this test imports NOTHING from libkb.agent.cascade / orchestrator. A new capability
    # agent is defined, registered, and dispatched purely through the registry seam.
    reg = AgentRegistry()

    class SummarizerAgent:
        card = AgentCard(
            id="summarizer",
            name="Summarizer",
            description="Shortens text.",
            skills=["summarize"],
            dispatchable=True,
        )

        def run(self, payload, emit=None):
            return {"summary": str(payload.get("text", ""))[:11]}

    reg.register(SummarizerAgent())

    assert reg.has("summarizer")
    out = reg.dispatch("summarizer", {"text": "hello world, this is long"})
    assert out["summary"] == "hello world"
    assert "summarizer" in {c.id for c in reg.cards()}


def test_agents_endpoint_lists_core_cards():
    from libkb.api.routes import agents

    data = agents()
    ids = {a["id"] for a in data["agents"]}
    assert {"librarian", "answerer", "verifier"} <= ids
    verifier = next(a for a in data["agents"] if a["id"] == "verifier")
    assert verifier["dispatchable"] is True
    assert "verify-numbers" in verifier["skills"]
