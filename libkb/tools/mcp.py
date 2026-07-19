"""The MCP seam — external tools/skills as registered capability agents (Phase C, D-061).

MCP (Model Context Protocol) is the open standard for connecting an agent to tools and data. We do
NOT reinvent it: an MCP server's tools are ADAPTED into shapes we already have —

  - a `CapabilityAgent` (`run(payload) -> dict`), so the registry can dispatch it and `/api/agents`
    discovers it, exactly like the Phase-B roles; and
  - a neutral `ToolSpec` (D-016), so the SAME tool can be offered to a tool-capable model in the
    tool-calling loop (Phase C.2).

The adapter needs only a name, a description, a JSON-schema, and a callable — so it wraps a real
MCP server or a plain local function. The seam is usable and unit-tested WITHOUT the `mcp` SDK, an
optional dependency (`pip install -e ".[mcp]"`) needed only to reach a real server over stdio.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from libkb.agent.roles.base import AgentCard, EmitFn
from libkb.agent.roles.registry import AgentRegistry
from libkb.llm.client import ToolSpec

# A tool is metadata + a callable: JSON-able args in, JSON-able result out.
ToolInvoke = Callable[[dict], Any]

_EMPTY_SCHEMA = {"type": "object", "properties": {}}


class McpToolAgent:
    """One tool, adapted to our `CapabilityAgent` interface. Built from plain metadata + an invoke
    callable, so it wraps a real MCP tool or a local function identically."""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict | None,
        invoke: ToolInvoke,
        *,
        server: str = "local",
    ) -> None:
        self._invoke = invoke
        self._name = name
        self.card = AgentCard(
            id=f"tool:{name}",
            name=name,
            description=description or f"MCP tool '{name}'",
            skills=["tool", f"mcp:{server}"],
            input_schema=input_schema or dict(_EMPTY_SCHEMA),
            output_schema={"result": "any"},
            dispatchable=True,
        )

    def run(self, payload: dict, emit: EmitFn | None = None) -> dict:
        """Dispatch the tool (A2A/MCP-style): JSON in, `{"result": ...}` out."""
        return {"result": self._invoke(payload)}

    def to_tool_spec(self) -> ToolSpec:
        """The neutral `ToolSpec` (D-016) for the model tool-calling loop — the same tool the
        registry dispatches, offered to a tool-capable model later (Phase C.2)."""
        return ToolSpec(
            name=self._name,
            description=self.card.description,
            parameters=self.card.input_schema or dict(_EMPTY_SCHEMA),
        )


def register_tool(
    registry: AgentRegistry,
    name: str,
    description: str,
    input_schema: dict | None,
    invoke: ToolInvoke,
    *,
    server: str = "local",
) -> str:
    """Register one tool (local skill or MCP-backed) as a capability agent. Returns its agent id.

    This is the whole extension seam: a new tool is a `register_tool()` call, never a change to the
    orchestrator or the cascade — the same guarantee Phase B proved for agents."""
    agent = McpToolAgent(name, description, input_schema, invoke, server=server)
    registry.register(agent)
    return agent.card.id


def register_mcp_server(
    registry: AgentRegistry,
    *,
    command: str,
    args: list[str] | None = None,
    name: str = "mcp",
) -> list[str]:
    """Connect to a REAL MCP server over stdio, list its tools, and register each (needs the
    optional `mcp` SDK). Each tool's invoke wires to the server's `call_tool`. Returns the ids.

    The whole point: after this call, an external MCP server's tools are indistinguishable from our
    own agents — discoverable in `/api/agents`, dispatchable through the registry."""
    client = _McpClient(command, args or [])
    ids: list[str] = []
    for tool_name, desc, schema in client.list_tools():
        ids.append(
            register_tool(
                registry,
                tool_name,
                desc,
                schema,
                invoke=lambda payload, _n=tool_name: client.call_tool(_n, payload),
                server=name,
            )
        )
    return ids


class _McpClient:
    """A thin synchronous wrapper over the async `mcp` stdio client. The optional/real path: it is
    exercised only when a real server is wired, so it is kept minimal. The unit-tested seam is the
    adapter above, which needs none of this."""

    def __init__(self, command: str, args: list[str]) -> None:
        self._command = command
        self._args = args

    @staticmethod
    def _require_mcp():
        try:
            import mcp  # noqa: F401
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:  # pragma: no cover - exercised only without the optional dep
            raise ImportError(
                "talking to a real MCP server needs the optional `mcp` SDK: "
                'install it with  pip install -e ".[mcp]"'
            ) from exc
        return ClientSession, StdioServerParameters, stdio_client

    def _run(self, op: str, tool: str | None, args: dict | None):
        import asyncio

        ClientSession, StdioServerParameters, stdio_client = self._require_mcp()

        async def _go():
            params = StdioServerParameters(command=self._command, args=self._args)
            async with (
                stdio_client(params) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                if op == "list":
                    listed = await session.list_tools()
                    return [
                        (t.name, t.description or "", dict(t.inputSchema or _EMPTY_SCHEMA))
                        for t in listed.tools
                    ]
                result = await session.call_tool(tool, args or {})
                return getattr(result, "structuredContent", None) or [
                    getattr(c, "text", "") for c in getattr(result, "content", [])
                ]

        return asyncio.run(_go())

    def list_tools(self) -> list[tuple[str, str, dict]]:  # pragma: no cover - optional dep
        return self._run("list", None, None)

    def call_tool(self, name: str, args: dict):  # pragma: no cover - optional dep
        return self._run("call", name, args)
