"""Agents as typed ROLES behind a registry (docs/AGENT_ARCHITECTURE.md, Phase B, D-061).

The cascade's steps become named agents — Librarian (triage), Answerer (compose), Verifier
(number-check) — each carrying an A2A-shaped `AgentCard` and registered in one place. The
orchestrator resolves them from the registry instead of hardcoding calls, so a new agent (a skill,
an MCP tool in Phase C) plugs in by registering, without loop surgery.
"""

from libkb.agent.roles.base import AgentCard, CapabilityAgent, EmitFn
from libkb.agent.roles.registry import AgentRegistry, get_registry

__all__ = ["AgentCard", "CapabilityAgent", "EmitFn", "AgentRegistry", "get_registry"]
