"""External tools & skills as registered capability agents (docs/AGENT_ARCHITECTURE.md, Phase C).

An MCP tool (or any callable skill) is adapted to the shapes Phase B built — a `CapabilityAgent`
for the registry/dispatch, and a neutral `ToolSpec` (D-016) for the model tool-calling loop — so a
tool plugs into the existing seam by registering, with no orchestrator change.
"""

from libkb.tools.mcp import McpToolAgent, register_mcp_server, register_tool

__all__ = ["McpToolAgent", "register_tool", "register_mcp_server"]
