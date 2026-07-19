"""The agent registry — one place agents are registered, discovered, and dispatched (Phase B).

The orchestrator resolves roles from HERE instead of importing concrete classes, so adding an agent
(a skill, an MCP tool in Phase C) is a `register()` call, never loop surgery. The falsifiable check
for this seam lives in tests/test_agent_roles.py: a brand-new agent registers and dispatches without
the orchestrator being touched.
"""

from __future__ import annotations

from libkb.agent.roles.base import AgentCard, EmitFn


class AgentRegistry:
    """A dict of id → agent. An agent needs a `.card`; a generically-dispatchable one also has
    `.run(payload) -> dict`."""

    def __init__(self) -> None:
        self._by_id: dict[str, object] = {}

    def register(self, agent: object) -> None:
        card = getattr(agent, "card", None)
        if not isinstance(card, AgentCard):
            raise TypeError("an agent must expose a `card: AgentCard`")
        self._by_id[card.id] = agent

    def get(self, agent_id: str) -> object:
        return self._by_id[agent_id]

    def has(self, agent_id: str) -> bool:
        return agent_id in self._by_id

    def cards(self) -> list[AgentCard]:
        return [a.card for a in self._by_id.values()]

    def dispatch(self, agent_id: str, payload: dict, emit: EmitFn | None = None) -> dict:
        """Invoke a capability agent generically (A2A/MCP-style). Raises if the agent is a pipeline
        role that has no generic `run` (it must be called through its typed method instead)."""
        agent = self._by_id[agent_id]
        run = getattr(agent, "run", None)
        if run is None:
            raise TypeError(f"agent '{agent_id}' is a pipeline role, not generically dispatchable")
        return run(payload, emit)


_default: AgentRegistry | None = None


def get_registry() -> AgentRegistry:
    """The process-wide default registry, populated lazily on first use with the built-in roles.

    Lazy on purpose: the cascade imports this module at load time, and the agent classes import back
    from the cascade — populating here (not at import) breaks the cycle."""
    global _default
    if _default is None:
        reg = AgentRegistry()
        from libkb.agent.roles.answerer import AnswererAgent
        from libkb.agent.roles.librarian import LibrarianAgent
        from libkb.agent.roles.routes import ConciergeAgent, SearchLibraryRoute
        from libkb.agent.roles.verifier import VerifierAgent

        reg.register(LibrarianAgent())
        reg.register(AnswererAgent())
        reg.register(VerifierAgent())
        # front-door routes (D-061): the orchestrator dispatches whole queries to these
        reg.register(ConciergeAgent())
        reg.register(SearchLibraryRoute())
        # Phase C.2: the calculator is both a dispatchable tool and a compute ROUTE
        from libkb.tools.calculator import CalculatorAgent, CalculatorRoute

        reg.register(CalculatorAgent())
        reg.register(CalculatorRoute())
        # skills: structural navigation + clarify-before-guessing (both routes, both defer safely)
        from libkb.agent.roles.catalog_nav import CatalogNavigatorRoute
        from libkb.agent.roles.clarify import ClarifyRoute

        reg.register(CatalogNavigatorRoute())
        reg.register(ClarifyRoute())
        _default = reg
    return _default
