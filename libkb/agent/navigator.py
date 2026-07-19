"""The walking librarian.

Runs an LLM tool loop in its OWN context (principle P7) and returns only
(path, pages, status) — the answering context never sees the menus it rejected.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

from libkb.agent.tools import (
    ASK_LIBRARIAN_SPEC,
    OPEN_SHELF_SPEC,
    REFRAME_SPEC,
    TOOL_SPECS,
    NavEvent,
    Navigation,
    Terminal,
)
from libkb.catalog.store import Catalog
from libkb.config import get_settings
from libkb.library.models import PageContent
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, ToolResponse, ToolSpec, Turn, get_llm

log = structlog.get_logger(__name__)

EventCB = Callable[[NavEvent], None]


@dataclass
class _FullPage:
    """A page read still sitting in `turns` at full length, waiting to be shelved."""

    turn: int  # index into `turns`
    slot: int  # index into that turn's tool_responses
    digest: str
    read_at: int = 0  # which tool turn it was read on; set by _shelve_old_pages' caller


def _shelve_old_pages(
    turns: list[Turn], full_pages: list[_FullPage], now: int, keep_full: int
) -> None:
    """Put the books back on the shelf (ROUTING_REDESIGN §6).

    Every LLM turn resends the whole conversation, so a page read early in a walk is re-billed on
    every later turn — even one the librarian read, rejected, and walked away from. Once a page's
    turn is `keep_full` turns old, its full text in `turns` is replaced by a short digest.

    This cannot cost the ANSWER anything: `compose_answer` builds its evidence from
    `NavState.pages`, which never enters this conversation. What it could cost is the navigator's
    own "have I got enough?" judgement — so the most recent page stays in full, and the falsifier is
    `answer_acc` (see evals/judge.py). `keep_full < 0` disables the whole mechanism.
    """
    if keep_full < 0:
        return
    for page in full_pages:
        if page.read_at == 0:
            page.read_at = now  # first sighting: this is the turn it was read on
        if now - page.read_at <= keep_full:
            continue
        responses = turns[page.turn].tool_responses
        if responses is None:
            continue
        slot = responses[page.slot]
        if slot.response.get("result") != page.digest:
            slot.response["result"] = page.digest


@dataclass
class NavResult:
    status: str  # FOUND | NOT_FOUND
    pages: list[PageContent] = field(default_factory=list)
    closest: list[str] = field(default_factory=list)
    hops: int = 0
    backtracks: int = 0
    reason: str = ""
    events: list[NavEvent] = field(default_factory=list)
    # the retrieval dials this query actually ran at (D-058 auto resolution), for the details panel
    resolved_fetch: int = 0
    resolved_basket: int = 0


def navigate(
    query: str,
    *,
    store: LibraryStore,
    llm: LLM | None = None,
    catalog: Catalog | None = None,
    event_cb: EventCB | None = None,
) -> NavResult:
    llm = llm or get_llm()
    settings = get_settings()
    # the query goes in so a shelf too wide to render can be SHORTLISTED against it (§7.5) rather
    # than falling back to the book gate the redesign exists to remove
    nav = Navigation(store, settings, catalog=catalog, llm=llm, query=query)

    # shelf mode: the agent never commits to a book — open_shelf replaces open_book, and the
    # prompt describes the shelf-scan workflow (docs/ROUTING_REDESIGN.md).
    if settings.routing_mode == "shelf":
        specs = [spec for spec in TOOL_SPECS if spec["name"] != "open_book"]
        specs.insert(1, OPEN_SHELF_SPEC)
        system = llm.load_prompt("route_shelf")
    else:
        specs = list(TOOL_SPECS)
        system = llm.load_prompt("route")
    specs.append(REFRAME_SPEC)  # the query is not frozen at t=0 (§8.3)
    if catalog is not None:
        specs.append(ASK_LIBRARIAN_SPEC)
    tools = [ToolSpec(**spec) for spec in specs]

    opening = (
        f"Reader's question: {query}\n\n{nav.start_menu()}\n\n"
        "Begin walking. Call exactly one tool now."
    )
    turns: list[Turn] = [Turn(role="user", text=opening)]

    terminal: Terminal | None = None
    # bound total LLM turns; generous over the hop budget to allow re-orientation
    max_steps = settings.max_hops + settings.max_pages_per_nav + 8
    empty_replies = 0
    tool_turns = 0
    full_pages: list[_FullPage] = []  # page reads still sitting in `turns` at full length

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
            if outcome.digest:
                full_pages.append(
                    _FullPage(turn=len(turns), slot=len(responses) - 1, digest=outcome.digest)
                )
            if outcome.event and event_cb:
                event_cb(outcome.event)
            if outcome.terminal and terminal is None:
                terminal = outcome.terminal
        turns.append(Turn(role="tool", tool_responses=responses))
        tool_turns += 1
        _shelve_old_pages(turns, full_pages, tool_turns, settings.page_digest_after_turns)
        if terminal is not None:
            break

    if terminal is None:
        # same rule as budget exhaustion: pages already read are evidence, not garbage
        if nav.state.pages:
            terminal = Terminal(
                status="FOUND",
                page_ids=[p.page_id for p in nav.state.pages],
                reason="walk did not conclude in budget — answering from the pages already read",
            )
        else:
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
