"""The librarian's tools and the walk state machine.

Hard budgets live HERE, in code — not in prompts (decision D-008). The navigator
(agent/navigator.py) drives an LLM tool loop; this module executes each call against
the LibraryStore, enforces limits, and emits a NavEvent per step for streaming/logging.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from libkb.config import Settings
from libkb.library.models import (
    ROOT_ID,
    NodeCard,
    NodeID,
    NodeRef,
    PageContent,
    TOCEntry,
    one_line_of,
)
from libkb.library.store import LibraryStore

# ------------------------------------------------------------------- events


@dataclass
class NavEvent:
    action: str  # enter | open | read | back | found | not_found | budget
    title: str
    kind: str | None = None  # domain | shelf | book | toc | page
    node_id: NodeID | None = None
    status: str = "done"  # done | backtracked | read | found | notfound | walking
    detail: str = ""
    snippet: str = ""


@dataclass
class Terminal:
    status: str  # FOUND | NOT_FOUND
    page_ids: list[NodeID] = field(default_factory=list)
    reason: str = ""
    closest: list[str] = field(default_factory=list)


@dataclass
class ToolOutcome:
    text: str  # returned to the model as the function response
    event: NavEvent | None = None
    terminal: Terminal | None = None


@dataclass
class NavState:
    cursor: NodeID
    path: list[NodeRef]
    visited: set[NodeID] = field(default_factory=set)
    hops: int = 0
    pages_read: int = 0
    librarian_calls: int = 0
    backtracks: int = 0
    trajectory: list[NavEvent] = field(default_factory=list)
    pages: list[PageContent] = field(default_factory=list)
    current_children: dict[str, NodeCard] = field(default_factory=dict)  # lower(title) → card
    current_toc: dict[str, TOCEntry] = field(default_factory=dict)  # lower(title) → entry
    open_book_id: NodeID | None = None


# The six P1 tools. ask_librarian (catalog shortcut) arrives with P2.
TOOL_SPECS = [
    {
        "name": "browse",
        "description": "Step into a domain or shelf by its exact title to see what is inside.",
        "parameters": {
            "type": "object",
            "properties": {"target": {"type": "string", "description": "Exact child title"}},
            "required": ["target"],
        },
    },
    {
        "name": "open_book",
        "description": "Open a book by its exact title to read its table of contents.",
        "parameters": {
            "type": "object",
            "properties": {"title": {"type": "string", "description": "Exact book title"}},
            "required": ["title"],
        },
    },
    {
        "name": "read_page",
        "description": "Read a page by its exact title from the book you currently have open.",
        "parameters": {
            "type": "object",
            "properties": {"title": {"type": "string", "description": "Exact page title"}},
            "required": ["title"],
        },
    },
    {
        "name": "go_back",
        "description": "Return to the previous room. Say briefly why you are leaving.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
    {
        "name": "found",
        "description": "Conclude: you have read pages that answer the question.",
        "parameters": {
            "type": "object",
            "properties": {"note": {"type": "string"}},
            "required": ["note"],
        },
    },
    {
        "name": "not_found",
        "description": "Conclude: the library does not hold this. Name the closest shelves seen.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "closest": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["reason"],
        },
    },
]


class Navigation:
    """One isolated walk over the library."""

    def __init__(self, store: LibraryStore, settings: Settings) -> None:
        self.store = store
        self.s = settings
        self.state = NavState(cursor=ROOT_ID, path=store.path_of(ROOT_ID))

    # ------------------------------------------------------------- rendering

    def start_menu(self) -> str:
        return self._render_menu(ROOT_ID)

    def _render_menu(self, node_id: NodeID) -> str:
        meta = self.store.get(node_id)
        cards = self.store.children(node_id)
        self.state.cursor = node_id
        self.state.path = self.store.path_of(node_id)
        self.state.visited.add(node_id)
        self.state.current_children = {c.title.lower(): c for c in cards}
        self.state.current_toc = {}
        self.state.open_book_id = None

        loc = self.store.path_str(node_id) or "the entrance"
        lines = [f"You are in: {loc}  [{meta.kind}]"]
        if meta.description:
            lines.append(f"Description: {meta.description}")
        if not cards:
            lines.append("\nThis room is empty — nothing is shelved here.")
        else:
            label = {"root": "Domains", "domain": "Shelves", "shelf": "Books and shelves"}.get(
                meta.kind, "Contents"
            )
            lines.append(f"\n{label} here:")
            for c in cards:
                bullet = f'  - "{c.title}"  [{c.kind}]'
                if c.one_line:
                    bullet += f" — {c.one_line}"
                lines.append(bullet)
                for hint in c.see_also:
                    lines.append(f"        (cross-link: {hint})")
        for sa in meta.see_also:
            lines.append(f"See also: {sa.note} — see: {sa.target.title}")
        return "\n".join(lines)

    def _render_toc(self, book_id: NodeID) -> str:
        meta = self.store.get(book_id)
        toc = self.store.toc(book_id)
        # cursor moves INTO the book so go_back returns to its shelf, not the domain.
        # current_children stays the shelf's list so the reader can switch sibling books.
        self.state.cursor = book_id
        self.state.path = self.store.path_of(book_id)
        self.state.visited.add(book_id)
        self.state.open_book_id = book_id
        self.state.current_toc = {}
        lines = [f"Opened book: {meta.title}"]
        if meta.description:
            lines.append(f"About: {meta.description}")
        lines.append("\nTable of contents:")
        for chapter in toc.chapters:
            lines.append(f"  {chapter.title}")
            for entry in chapter.entries:
                self.state.current_toc[entry.title.lower()] = entry
                row = f'    - "{entry.title}"'
                if entry.one_line:
                    row += f" — {entry.one_line}"
                lines.append(row)
        lines.append('\nUse read_page("<title>") to read a page.')
        return "\n".join(lines)

    # -------------------------------------------------------------- dispatch

    def execute(self, name: str, args: dict) -> ToolOutcome:
        handler = {
            "browse": self._browse,
            "open_book": self._open_book,
            "read_page": self._read_page,
            "go_back": self._go_back,
            "found": self._found,
            "not_found": self._not_found,
        }.get(name)
        if handler is None:
            return ToolOutcome(text=f"Unknown tool '{name}'.")
        outcome = handler(args)
        if outcome.event:
            self.state.trajectory.append(outcome.event)
        return outcome

    # --------------------------------------------------------------- handlers

    def _browse(self, args: dict) -> ToolOutcome:
        card = self._resolve_child(args.get("target", ""))
        if card is None:
            return ToolOutcome(text=self._not_here(args.get("target", "")))
        if card.kind == "book":  # tolerant: browsing a book == opening it
            return self._open_book({"title": card.title})
        if self.state.hops + 1 > self.s.max_hops:
            return self._budget_exhausted()
        self.state.hops += 1
        menu = self._render_menu(card.id)
        event = NavEvent("enter", card.title, card.kind, card.id, "done", detail=card.one_line)
        return ToolOutcome(text=menu, event=event)

    def _open_book(self, args: dict) -> ToolOutcome:
        card = self._resolve_child(args.get("title", ""))
        if card is None or card.kind != "book":
            return ToolOutcome(text=self._not_here(args.get("title", ""), expected="book"))
        if self.state.hops + 1 > self.s.max_hops:
            return self._budget_exhausted()
        self.state.hops += 1
        self.state.visited.add(card.id)
        toc = self._render_toc(card.id)
        event = NavEvent("open", card.title, "book", card.id, "done", detail=card.one_line)
        return ToolOutcome(text=toc, event=event)

    def _read_page(self, args: dict) -> ToolOutcome:
        title = args.get("title", "")
        entry = self.state.current_toc.get(title.lower().strip())
        if entry is None:
            entry = self._fuzzy_toc(title)
        if entry is None:
            if not self.state.current_toc:
                return ToolOutcome(text="No book is open. Use open_book(title) first.")
            return ToolOutcome(text=self._not_here(title, expected="page"))
        if self.state.pages_read >= self.s.max_pages_per_nav:
            return ToolOutcome(
                text="Page budget reached — conclude now with found() or not_found()."
            )
        page = self.store.page(entry.page_id)
        self.state.pages.append(page)
        self.state.pages_read += 1
        block = f"[PAGE — {self.store.path_str(page.page_id)}]\n<<<\n{page.markdown}\n>>>"
        event = NavEvent(
            "read",
            page.title,
            "page",
            page.page_id,
            "read",
            snippet=one_line_of(page.markdown, 120),
        )
        return ToolOutcome(text=block, event=event)

    def _go_back(self, args: dict) -> ToolOutcome:
        reason = args.get("reason", "")
        parent_id = self._parent_of(self.state.cursor)
        left = self.store.get(self.state.cursor)
        self.state.backtracks += 1
        event = NavEvent("back", left.title, left.kind, left.id, "backtracked", detail=reason)
        menu = self._render_menu(parent_id)
        return ToolOutcome(text="Returned.\n\n" + menu, event=event)

    def _found(self, args: dict) -> ToolOutcome:
        if not self.state.pages:
            return ToolOutcome(
                text="You have not read any page yet. Use read_page() before found()."
            )
        note = args.get("note", "")
        terminal = Terminal(
            status="FOUND", page_ids=[p.page_id for p in self.state.pages], reason=note
        )
        event = NavEvent("found", "FOUND", None, None, "found", detail=note)
        return ToolOutcome(text="Concluded: FOUND.", event=event, terminal=terminal)

    def _not_found(self, args: dict) -> ToolOutcome:
        reason = args.get("reason", "")
        closest = args.get("closest") or self._sibling_titles()
        terminal = Terminal(status="NOT_FOUND", reason=reason, closest=list(closest))
        event = NavEvent("not_found", "NOT FOUND", None, None, "notfound", detail=reason)
        return ToolOutcome(text="Concluded: NOT_FOUND.", event=event, terminal=terminal)

    # --------------------------------------------------------------- helpers

    def _resolve_child(self, title: str) -> NodeCard | None:
        key = title.lower().strip()
        card = self.state.current_children.get(key)
        if card:
            return card
        for name, candidate in self.state.current_children.items():  # forgiving substring match
            if key and (key in name or name in key):
                return candidate
        return None

    def _fuzzy_toc(self, title: str) -> TOCEntry | None:
        key = title.lower().strip()
        for name, entry in self.state.current_toc.items():
            if key and (key in name or name in key):
                return entry
        return None

    def _parent_of(self, node_id: NodeID) -> NodeID:
        if node_id == ROOT_ID:
            return ROOT_ID
        meta = self.store.get(node_id)
        return meta.parent_id or ROOT_ID

    def _sibling_titles(self) -> list[str]:
        return [c.title for c in self.state.current_children.values()]

    def _not_here(self, target: str, expected: str = "item") -> str:
        options = ", ".join(f'"{c.title}"' for c in self.state.current_children.values())
        return (
            f'No {expected} titled "{target}" is here. '
            f"Available: {options or 'nothing'}. "
            "Use the exact title, or go_back(reason) to try another room."
        )

    def _budget_exhausted(self) -> ToolOutcome:
        event = NavEvent("budget", "budget exhausted", None, None, "notfound")
        terminal = Terminal(status="NOT_FOUND", reason="hop budget exhausted")
        return ToolOutcome(text="Hop budget exhausted.", event=event, terminal=terminal)
