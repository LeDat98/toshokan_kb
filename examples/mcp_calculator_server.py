"""A tiny sample MCP server — a calculator — for the Phase C end-to-end demo (D-061).

Run it via LibraryKB's MCP seam (needs the optional dep: `pip install -e ".[mcp]"`):

    from libkb.agent.roles.registry import get_registry
    from libkb.tools import register_mcp_server

    ids = register_mcp_server(
        get_registry(), command="python", args=["examples/mcp_calculator_server.py"], name="calc"
    )
    # now the calculator's tools are registered agents:
    get_registry().dispatch("tool:add", {"a": 2, "b": 3})        # -> {"result": 5}
    get_registry().dispatch("tool:multiply", {"a": 4, "b": 5})   # -> {"result": 20}

They also show up in GET /api/agents and as A2A skills in GET /api/a2a/agent-card — with no change
to the cascade or the orchestrator. That is the Phase C guarantee.
"""

from __future__ import annotations


def main() -> None:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("calculator")

    @server.tool()
    def add(a: float, b: float) -> float:
        """Add two numbers."""
        return a + b

    @server.tool()
    def multiply(a: float, b: float) -> float:
        """Multiply two numbers."""
        return a * b

    server.run()


if __name__ == "__main__":
    main()
