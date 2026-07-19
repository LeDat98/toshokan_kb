"""The catalog-navigator ROUTE (D-061): answers questions about the library's STRUCTURE — what
domains/shelves/books it holds, how many, what's inside a container — deterministically from the
store, never from the model's memory.

The split from `search_library` is deliberate: the navigator answers "what is IN the library"
(inventory); the cascade answers "what does the library SAY about a topic" (content). The model only
PARSES the request into a structured query; the answer is read from the store, so it cannot invent a
domain or a count. If the parse says the message is not structural, the route defers to the library.
"""

from __future__ import annotations

from libkb.agent.answerer import Answer
from libkb.agent.navigator import NavResult
from libkb.agent.roles.base import AgentCard
from libkb.agent.roles.routes import RouteContext
from libkb.agent.tools import NavEvent
from libkb.library.models import ROOT_ID
from libkb.llm.client import get_llm

_CONTAINERS = ("domain", "shelf", "book")

NAV_SCHEMA = {
    "type": "object",
    "properties": {
        "list": {
            "type": "string",
            "enum": ["domains", "shelves", "books", "pages", "overview", "none"],
        },
        "under": {"type": "string"},
    },
    "required": ["list"],
}


def _descendants(store, node_id: str, kind: str) -> list:
    out = []
    for child in store.children(node_id):
        if child.kind == kind:
            out.append(child)
        if child.kind in _CONTAINERS:
            out.extend(_descendants(store, child.id, kind))
    return out


def _find(store, name: str):
    """Best-effort node lookup by title (exact, then substring) across domains/shelves/books."""
    target = name.strip().lower()
    if not target:
        return None
    frontier = list(store.children(ROOT_ID))
    substr = None
    while frontier:
        node = frontier.pop()
        title = node.title.lower()
        if title == target:
            return node
        if substr is None and target in title:
            substr = node
        if node.kind in ("domain", "shelf"):
            frontier.extend(store.children(node.id))
    return substr


def _line(kind: str, titles: list[str], scope: str) -> str:
    if not titles:
        return f"{scope} has no {kind}s."
    plural = kind + ("s" if len(titles) != 1 else "")
    return f"{scope} has {len(titles)} {plural}: {', '.join(titles)}."


def _describe(store, what: str, under: str) -> str | None:
    scope_id, scope_title = ROOT_ID, "The library"
    if under:
        node = _find(store, under)
        if node is None:
            doms = [c.title for c in store.children(ROOT_ID) if c.kind == "domain"]
            return f"I don't have '{under}'. I hold these domains: {', '.join(doms)}."
        scope_id, scope_title = node.id, node.title

    if what == "domains":
        doms = [c.title for c in store.children(ROOT_ID) if c.kind == "domain"]
        return _line("domain", doms, "The library")
    if what == "shelves":
        return _line(
            "shelf", [n.title for n in _descendants(store, scope_id, "shelf")], scope_title
        )
    if what == "books":
        return _line("book", [n.title for n in _descendants(store, scope_id, "book")], scope_title)
    if what == "pages":
        n = len(_descendants(store, scope_id, "page"))
        return f"{scope_title} holds {n} page(s)."
    if what == "overview":
        st = store.get(ROOT_ID).stats
        doms = [c.title for c in store.children(ROOT_ID) if c.kind == "domain"]
        return (
            f"The library holds {len(doms)} domain(s) ({', '.join(doms)}): "
            f"{st.n_shelves} shelves, {st.n_books} books, {st.n_pages} pages."
        )
    return None  # "none" — not a structural question


class CatalogNavigatorRoute:
    """The `catalog` route: structural questions about the library, answered from the store."""

    card = AgentCard(
        id="catalog",
        name="Catalog navigator",
        description="Answers questions about the library's STRUCTURE — which domains/shelves/books "
        "exist, how many, and what's inside a container — read straight from the catalog.",
        skills=["catalog", "navigate", "inventory"],
        route_when="a question about what the library CONTAINS (structure) rather than a topic — "
        "'what domains do you have?', 'how many books in Retail?', 'list the shelves in AI'",
    )

    def handle(self, ctx: RouteContext) -> tuple[Answer, NavResult] | None:
        llm = ctx.llm or get_llm()
        try:
            data = llm.generate_json(
                llm.load_prompt("catalog_nav", query=ctx.query),
                schema=NAV_SCHEMA,
                model=ctx.settings.model_lite,
            )
            what = str(data.get("list") or "").strip()
            under = str(data.get("under") or "").strip()
        except Exception:
            return None
        text = _describe(ctx.store, what, under)
        if text is None:
            return None  # not structural → let the library answer
        events = [
            NavEvent(
                "thought",
                "This is about the library's structure — reading the catalog.",
                None,
                None,
                "done",
                detail="route",
            ),
            NavEvent("found", "read the catalog", None, None, "found", detail="catalog"),
        ]
        if ctx.emit:
            for ev in events:
                ctx.emit(ev)
        answer = Answer(text=text, status="answered", confidence="high")
        return answer, NavResult(status="FOUND", reason="catalog", events=events)
