"""Phase C (D-061): the MCP/tool seam — a tool plugs into the SAME registry seam as a Phase-B agent.

The load-bearing test is `test_local_tool_plugs_into_the_registry_seam`: a calculator tool is
registered and dispatched end-to-end through the registry with NO import of, or edit to, the
cascade/orchestrator. A real MCP server's tools reach the system by exactly this path (via
`register_mcp_server`); this test exercises the seam with a local callable so it needs neither the
optional `mcp` SDK nor a subprocess.
"""

from __future__ import annotations

import importlib.util

import pytest

from libkb.agent.roles.registry import AgentRegistry
from libkb.llm.client import ToolSpec
from libkb.tools import McpToolAgent, register_mcp_server, register_tool


def test_local_tool_plugs_into_the_registry_seam():
    # NOTE: nothing from libkb.agent.cascade / orchestrator is imported — a tool is just an agent.
    reg = AgentRegistry()
    tool_id = register_tool(
        reg,
        "add",
        "Add two numbers.",
        {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}},
        invoke=lambda p: p["a"] + p["b"],
    )
    assert tool_id == "tool:add"
    assert reg.has("tool:add")

    out = reg.dispatch("tool:add", {"a": 2, "b": 3})
    assert out == {"result": 5}

    # discoverable and marked as a dispatchable tool, exactly like a Phase-B capability agent
    card = next(c for c in reg.cards() if c.id == "tool:add")
    assert card.dispatchable is True
    assert "tool" in card.skills


def test_tool_bridges_to_a_neutral_tool_spec():
    # The SAME tool the registry dispatches can be offered to a tool-capable model (D-016 ToolSpec).
    agent = McpToolAgent(
        "multiply",
        "Multiply two numbers.",
        {"type": "object", "properties": {"a": {"type": "number"}}},
        invoke=lambda p: p["a"] * p.get("b", 1),
    )
    spec = agent.to_tool_spec()
    assert isinstance(spec, ToolSpec)
    assert spec.name == "multiply"
    assert spec.description == "Multiply two numbers."
    assert spec.parameters["properties"]["a"]["type"] == "number"


@pytest.mark.skipif(
    importlib.util.find_spec("mcp") is not None, reason="the mcp SDK is installed here"
)
def test_register_mcp_server_without_the_sdk_fails_loudly():
    # Without the optional dep, reaching a real server must raise a clear, actionable error — not a
    # silent no-op. (When mcp IS installed this would spawn a subprocess, so the test is skipped.)
    reg = AgentRegistry()
    with pytest.raises(ImportError):
        register_mcp_server(reg, command="python", args=["examples/mcp_calculator_server.py"])


def test_a2a_agent_card_exposes_our_skills():
    from libkb.api.routes import a2a_agent_card

    card = a2a_agent_card()
    assert card["name"] == "LibraryKB"
    assert card["capabilities"]["streaming"] is True
    ids = {s["id"] for s in card["skills"]}
    assert {"librarian", "answerer", "verifier"} <= ids
