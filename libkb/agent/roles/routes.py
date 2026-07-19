"""Front-door ROUTES and the orchestrator's route decision (D-061).

Routing is the orchestrator's own job — deciding, per message, which capability handles the whole
query: answer a greeting directly, or search the library (the default), or (later) call a tool. The
choices are DATA-DRIVEN: any capability whose card sets `route_when` shows up in the menu, so a new
route (or a Phase-C tool) becomes selectable by registering, with no change to the decision
code. Two guardrails: the decision is biased to `search_library` (a knowledge question must never be
answered from the model's own memory — P6), and it fails to `search_library` on any error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from libkb.agent.answerer import Answer
from libkb.agent.navigator import NavResult
from libkb.agent.roles.base import AgentCard
from libkb.agent.roles.registry import AgentRegistry
from libkb.agent.tools import NavEvent
from libkb.config import Settings
from libkb.library.models import ROOT_ID
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {"route": {"type": "string"}, "reason": {"type": "string"}},
    "required": ["route"],
}
CONCIERGE_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}

DEFAULT_ROUTE = "search_library"


@dataclass
class RouteContext:
    query: str
    store: LibraryStore
    llm: LLM | None
    settings: Settings
    emit: object | None = None  # an event callback (NavEvent) -> None, or None


def _library_overview(store: LibraryStore) -> str:
    """A one-line, TRUE description of what the library holds — read from the store, no LLM. This is
    the only 'knowledge' the concierge may use, so a meta answer is grounded, not invented."""
    try:
        root = store.get(ROOT_ID)
        domains = [c.title for c in store.children(ROOT_ID) if c.kind == "domain"]
        st = root.stats
        head = f"{len(domains)} domain(s)" + (f" ({', '.join(domains)})" if domains else "")
        return (
            f"The library holds {head}: {st.n_shelves} shelves, "
            f"{st.n_books} books, {st.n_pages} pages."
        )
    except Exception:
        return "A hierarchical library of documents."


class ConciergeAgent:
    """The `answer_directly` route: greetings and questions ABOUT the assistant — no library search.
    Grounded ONLY in the persona (its defined behaviour) and a true overview of the library, never
    the model's world knowledge."""

    card = AgentCard(
        id="answer_directly",
        name="Concierge",
        description="Answers greetings, thanks, small talk, and questions about the assistant "
        "(who/what/how) — from its persona and a true overview of the library, no search.",
        skills=["greeting", "meta", "smalltalk"],
        route_when="greetings, thanks, small talk, or questions ABOUT the assistant itself "
        "(who are you, what can you do, how do you work) — needs no library lookup",
    )

    def handle(self, ctx: RouteContext) -> tuple[Answer, NavResult]:
        llm = ctx.llm or get_llm()
        persona = llm.load_prompt("persona")
        overview = _library_overview(ctx.store)
        prompt = llm.load_prompt("concierge", persona=persona, overview=overview, query=ctx.query)
        try:
            data = llm.generate_json(prompt, schema=CONCIERGE_SCHEMA)
            text = str(data.get("answer") or "").strip()
        except Exception:
            text = ""
        if not text:
            text = (
                "Hello! I'm the librarian — ask me a question and I'll search the library for you."
            )
        events = [
            NavEvent(
                "thought",
                "This needs no library search — answering directly.",
                None,
                None,
                "done",
                detail="route",
            ),
            NavEvent("found", "answered directly", None, None, "found", detail="concierge"),
        ]
        if ctx.emit:
            for ev in events:
                ctx.emit(ev)
        answer = Answer(text=text, status="answered", confidence="high")
        nav = NavResult(status="FOUND", reason="concierge", events=events)
        return answer, nav


class SearchLibraryRoute:
    """The `search_library` route — a menu entry for the DEFAULT knowledge path (shortcut → cascade
    → walk). It has no `handle`: the orchestrator runs its existing knowledge path for this route,
    so the foundation is untouched."""

    card = AgentCard(
        id="search_library",
        name="Search the library",
        description="The cascade: sieve the shelves, judge the candidates, read the basket, answer "
        "with citations — or an honest NOT_FOUND. The default for any knowledge question.",
        skills=["retrieve", "cascade"],
        route_when="ANY question that might be answered from the library — the DEFAULT; "
        "when unsure, choose this",
    )


# ── the decision ────────────────────────────────────────────────────────────────────────────────

# A tight allow-list of trivial openers (vi+en) handled with ZERO model calls. Kept narrow so
# anything not obviously a greeting goes to the lite classifier, which is biased to the library.
_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "yo",
    "hiya",
    "hello there",
    "good morning",
    "good afternoon",
    "good evening",
    "howdy",
    "thanks",
    "thank you",
    "thanks a lot",
    "thank you very much",
    "thx",
    "ty",
    "cheers",
    "bye",
    "goodbye",
    "see you",
    "see ya",
    "chào",
    "chào bạn",
    "xin chào",
    "alo",
    "hế lô",
    "cảm ơn",
    "cám ơn",
    "cảm ơn bạn",
    "cám ơn bạn",
    "cảm ơn nhé",
    "tạm biệt",
}


def _is_trivial_greeting(query: str) -> bool:
    q = re.sub(r"[!.?,~…\s]+$", "", query.strip().lower())
    q = re.sub(r"\s+", " ", q).strip()
    return bool(q) and len(q.split()) <= 4 and q in _GREETINGS


def routes_from_registry(registry: AgentRegistry) -> dict[str, AgentCard]:
    """The route MENU — every registered capability whose card declares `route_when`. Registering a
    new route (or a Phase-C tool) adds it here with no change to `decide_route`."""
    return {c.id: c for c in registry.cards() if c.route_when}


def decide_route(query: str, llm: LLM, settings: Settings, routes: dict[str, AgentCard]) -> str:
    """Pick one route id from the menu. Biased to `search_library`; fails to it on any error."""
    if "answer_directly" in routes and _is_trivial_greeting(query):
        return "answer_directly"
    try:
        menu = "\n".join(f"- {rid}: {card.route_when}" for rid, card in routes.items())
        prompt = llm.load_prompt("route_query", query=query, routes=menu)
        data = llm.generate_json(prompt, schema=ROUTE_SCHEMA, model=settings.model_lite)
        choice = str(data.get("route") or "").strip()
        if choice in routes:
            return choice
    except Exception:
        pass
    return DEFAULT_ROUTE
