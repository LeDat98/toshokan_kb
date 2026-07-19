"""The role contract: an A2A-shaped descriptor + a duck-typed agent (D-061, Phase B).

Two tiers, deliberately:
  - Every agent carries an `AgentCard` — an A2A-shaped self-description (id, skills, I/O) so it
    can be DISCOVERED and delegated to. Conforming to the A2A shape costs no framework, just this
    dataclass.
  - A **capability agent** is additionally generically dispatchable: `run(payload) -> dict`, JSON
    in, JSON out — the shape MCP tools and external A2A agents speak. The Verifier is one; Phase C
    tools will be too. The PIPELINE roles (Librarian, Answerer) operate on live objects (store,
    LLM), so they expose typed methods and are not generically dispatchable — they still carry a
    card for discovery. The framework supports both on purpose.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

EmitFn = Callable[[Any], None]


@dataclass(frozen=True)
class AgentCard:
    """How an agent announces itself — the A2A "agent card" shape, trimmed to what we use."""

    id: str
    name: str
    description: str
    skills: list[str] = field(default_factory=list)
    input_schema: dict | None = None
    output_schema: dict | None = None
    dispatchable: bool = False  # True ⇒ implements run(payload)->dict (A2A/MCP-style)
    # Set ⇒ this capability is a FRONT-DOOR ROUTE the orchestrator can send a whole query to; the
    # text is the "use this route when…" line it reads to decide (D-061). None ⇒ internal role/tool.
    route_when: str | None = None


@runtime_checkable
class CapabilityAgent(Protocol):
    """A generically-dispatchable agent: a JSON payload in, a JSON dict out. What MCP tools and
    external A2A agents look like from our side."""

    card: AgentCard

    def run(self, payload: dict, emit: EmitFn | None = None) -> dict: ...
