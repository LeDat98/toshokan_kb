"""The walking librarian.

Runs an LLM tool loop in its OWN context (principle P7) and returns only
(path, pages, status) — the answering context never sees the menus it rejected.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

from libkb.agent.tools import TOOL_SPECS, NavEvent, Navigation, Terminal
from libkb.config import get_settings
from libkb.library.models import PageContent
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, ToolResponse, ToolSpec, Turn, get_llm

log = structlog.get_logger(__name__)

EventCB = Callable[[NavEvent], None]


@dataclass
class NavResult:
    status: str  # FOUND | NOT_FOUND
    pages: list[PageContent] = field(default_factory=list)
    closest: list[str] = field(default_factory=list)
    hops: int = 0
    backtracks: int = 0
    reason: str = ""
    events: list[NavEvent] = field(default_factory=list)


def navigate(
    query: str,
    *,
    store: LibraryStore,
    llm: LLM | None = None,
    event_cb: EventCB | None = None,
) -> NavResult:
    llm = llm or get_llm()
    settings = get_settings()
    nav = Navigation(store, settings)
    system = llm.load_prompt("route")
    tools = [ToolSpec(**spec) for spec in TOOL_SPECS]

    opening = (
        f"Reader's question: {query}\n\n{nav.start_menu()}\n\n"
        "Begin walking. Call exactly one tool now."
    )
    turns: list[Turn] = [Turn(role="user", text=opening)]

    terminal: Terminal | None = None
    # bound total LLM turns; generous over the hop budget to allow re-orientation
    max_steps = settings.max_hops + settings.max_pages_per_nav + 8
    empty_replies = 0

    for _ in range(max_steps):
        result = llm.generate(turns, system=system, tools=tools, temperature=0.1)

        if not result.tool_calls:
            empty_replies += 1
            turns.append(Turn(role="model", text=result.text or ""))
            if empty_replies >= 2:
                break
            turns.append(
                Turn(
                    role="user",
                    text="Do not answer in prose. Call exactly one tool "
                    "(browse/open_book/read_page/go_back/found/not_found).",
                )
            )
            continue

        empty_replies = 0
        turns.append(Turn(role="model", tool_calls=result.tool_calls))
        responses: list[ToolResponse] = []
        for call in result.tool_calls:
            outcome = nav.execute(call.name, call.args)
            responses.append(ToolResponse(name=call.name, response={"result": outcome.text}))
            if outcome.event and event_cb:
                event_cb(outcome.event)
            if outcome.terminal and terminal is None:
                terminal = outcome.terminal
        turns.append(Turn(role="tool", tool_responses=responses))
        if terminal is not None:
            break

    if terminal is None:
        terminal = Terminal(status="NOT_FOUND", reason="walk did not conclude in budget")

    log.info(
        "navigate_done",
        status=terminal.status,
        hops=nav.state.hops,
        backtracks=nav.state.backtracks,
        pages=len(nav.state.pages),
    )
    return NavResult(
        status=terminal.status,
        pages=nav.state.pages if terminal.status == "FOUND" else [],
        closest=terminal.closest,
        hops=nav.state.hops,
        backtracks=nav.state.backtracks,
        reason=terminal.reason,
        events=nav.state.trajectory,
    )
