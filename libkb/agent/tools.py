"""The librarian's tools and the walk state machine.

Hard budgets live HERE, in code — not in prompts (decision D-008). The navigator
(agent/navigator.py) drives an LLM tool loop; this module executes each call against
the LibraryStore, enforces limits, and emits a NavEvent per step for streaming/logging.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from libkb.config import Settings
from libkb.exceptions import NodeNotFound
from libkb.library.models import (
    ROOT_ID,
    NodeCard,
    NodeID,
    NodeMeta,
    NodeRef,
    PageContent,
    TOCEntry,
    one_line_of,
)
from libkb.library.store import LibraryStore

if TYPE_CHECKING:
    from libkb.catalog.store import Catalog
    from libkb.llm.client import LLM

# ------------------------------------------------------------------- events


@dataclass
class NavEvent:
    # enter | open | shelf | read | back | found | not_found | budget | ask | lookup | reframe
    action: str
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
    # A compressed stand-in the navigator swaps in once this turn is old (§6). Only page reads set
    # it — they are the only tool response big enough to be worth re-billing on every later turn.
    digest: str | None = None


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
    reframes: int = 0
    reframed_from: list[str] = field(default_factory=list)  # reader's words → library's words


# The six core walk tools. ASK_LIBRARIAN_SPEC (below) is appended by the navigator only when a
# card catalog is loaded.
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

# Replaces open_book when routing_mode="shelf" (docs/ROUTING_REDESIGN.md). The book stays as
# storage/citation; it just stops being a decision the agent has to commit to.
OPEN_SHELF_SPEC = {
    "name": "open_shelf",
    "description": (
        "Lay out every page on the shelf you are standing on, grouped by the book it came from. "
        "You do not choose a book — scan the whole shelf, then read the page you want."
    ),
    "parameters": {"type": "object", "properties": {}},
}

# Bates (1989): a real search is berrypicking — the query is REWRITTEN at every stop, using the
# vocabulary just learned. LibraryKB used to freeze the reader's words at t=0 and never revise them,
# which is exactly the vocabulary gap the recall probe measures (§8.3).
REFRAME_SPEC = {
    "name": "reframe",
    "description": (
        "Restate the question in the library's own words once a room has taught you its "
        "vocabulary — e.g. the reader asked 'why did sales drop', this shelf calls it "
        "'basket-size decline root-cause'. Use it when the menus name a concept the reader did not."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "new_query": {"type": "string", "description": "The question in the library's words"},
            "why": {"type": "string", "description": "What you learned that prompted the rewrite"},
        },
        "required": ["new_query", "why"],
    },
}

# Offered only when a card catalog is loaded (P2c). It returns suggested page PATHS, not the
# answer — the librarian still walks there and verifies, so budgets and citations still hold.
ASK_LIBRARIAN_SPEC = {
    "name": "ask_librarian",
    "description": (
        "Consult the card catalog for pages matching a question. Returns suggested page paths "
        "to walk toward — useful when you are unsure which room to enter. Use it sparingly."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What you are looking for, in words"}
        },
        "required": ["query"],
    },
}


class Navigation:
    """One isolated walk over the library."""

    def __init__(
        self,
        store: LibraryStore,
        settings: Settings,
        *,
        catalog: Catalog | None = None,
        llm: LLM | None = None,
        query: str = "",
    ) -> None:
        self.store = store
        self.s = settings
        self.catalog = catalog
        self.llm = llm
        self.query = query  # the reader's question — the shelf shortlist ranks against it (§7)
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
                spine = _spine(c.one_line, self.s.max_one_line_chars)
                if spine:
                    bullet += f" — {spine}"
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
                spine = _spine(entry.one_line, self.s.max_one_line_chars)
                if spine:
                    row += f" — {spine}"
                lines.append(row)
        lines.append('\nUse read_page("<title>") to read a page.')
        return "\n".join(lines)

    def _shelf_contents(self, shelf_id: NodeID) -> tuple[list[NodeCard], list[tuple]]:
        books = [c for c in self.store.children(shelf_id) if c.kind == "book"]
        pairs = [
            (book, entry)
            for book in books
            for chapter in self.store.toc(book.id).chapters
            for entry in chapter.entries
        ]
        return books, pairs

    def _over_budget(self, pairs: list[tuple], rendered: str) -> str:
        """Why this shelf cannot be laid out in one menu — or "" if it can.

        Two independent ceilings, because a menu can be unusable for two unrelated reasons: too many
        OPTIONS to rank (an LLM's accuracy decays with option count, however short each one is), and
        too many TOKENS (the menu is resent on every later turn, so its price is paid once per
        remaining hop). Counting rows alone would wave through a 50-page shelf whose menu is 14k
        tokens — which is exactly what the shipped guard used to do.
        """
        if len(pairs) > self.s.max_shelf_toc_entries:
            return f"{len(pairs)} pages — more options than the librarian can rank at once"
        est = _estimate_tokens(rendered)
        if est > self.s.max_shelf_menu_tokens:
            return f"~{est} tokens — too heavy to carry through the rest of the walk"
        return ""

    def _shelf_over_budget(self) -> bool:
        """Is the shelf the cursor stands on too wide to lay out? Decides whether open_book is a
        harmless alias or a real escape hatch."""
        try:
            if self.store.get(self.state.cursor).kind != "shelf":
                return False
        except NodeNotFound:
            return False
        books, pairs = self._shelf_contents(self.state.cursor)
        if not pairs:
            return False
        return bool(self._over_budget(pairs, self._shelf_lines(self.state.cursor, books, pairs)))

    def _shelf_lines(self, shelf_id: NodeID, books: list[NodeCard], pairs: list[tuple]) -> str:
        meta = self.store.get(shelf_id)
        lines = [f"You are in: {self.store.path_str(shelf_id)}  [shelf]"]
        if meta.description:
            lines.append(f"Description: {meta.description}")
        lines.append(f"\nEverything on this shelf ({len(books)} books, {len(pairs)} pages):")
        for book in books:
            entries = [e for b, e in pairs if b.id == book.id]
            if not entries:
                continue
            lines.append(f'\n  From "{book.title}":')
            for entry in entries:
                row = f'    - "{entry.title}"'
                spine = _spine(entry.one_line, self.s.max_one_line_chars)
                if spine:
                    row += f" — {spine}"
                lines.append(row)
        # Cross-references: pages that LIVE on another shelf but that a reader looking at this one
        # would expect to find here (library/crosslinks.py, §8.1). They are added to the menu and to
        # current_toc, so the librarian can actually READ them — a cross-link he cannot follow is
        # decoration. Purely additive: nothing on this shelf is hidden, and the citation still
        # reports the page's true home.
        cross = self._crosslinks(books)
        if cross:
            lines.append("\n  Cross-references (shelved elsewhere, but they belong here):")
            for entry, home in cross:
                lines.append(f'    - "{entry.title}"   [filed under {home}]')

        lines.append(
            '\nUse read_page("<title>") to read any page above. You do not need to pick a book.'
        )
        return "\n".join(lines)

    def _render_shelf(self, shelf_id: NodeID) -> ToolOutcome:
        """The union of every book's TOC on this shelf. The book groups the pages for context but
        is NOT a decision — the agent picks a page directly (docs/ROUTING_REDESIGN.md §2)."""
        meta = self.store.get(shelf_id)
        books, pairs = self._shelf_contents(shelf_id)
        if not pairs:
            return ToolOutcome(text="This shelf holds no pages yet. go_back(reason) to leave.")

        text = self._shelf_lines(shelf_id, books, pairs)
        over = self._over_budget(pairs, text)
        if over:
            return self._too_wide(shelf_id, meta, books, pairs, over)

        cross = self._crosslinks(books)
        self.state.current_toc = {entry.title.lower(): entry for _, entry in pairs}
        for entry, _home in cross:
            # setdefault: a cross-ref must never shadow a page that really is on this shelf
            self.state.current_toc.setdefault(entry.title.lower(), entry)
        self.state.open_book_id = None
        self.state.visited.add(shelf_id)
        detail = f"{len(books)} books · {len(pairs)} pages · ~{_estimate_tokens(text)} tokens"
        if cross:
            detail += f" · {len(cross)} cross-refs"
        event = NavEvent("shelf", meta.title, "shelf", shelf_id, "done", detail=detail)
        return ToolOutcome(text=text, event=event)

    def _too_wide(
        self,
        shelf_id: NodeID,
        meta: NodeMeta,
        books: list[NodeCard],
        pairs: list[tuple[NodeCard, TOCEntry]],
        why: str,
    ) -> ToolOutcome:
        """A shelf too wide to lay out. Do NOT re-impose the book gate — that is the very mistake
        Part I of the redesign exists to undo. Instead run the two-stage recipe (§5, §7.5):
        **shortlist, then let the librarian compare**.

        The catalog earns this job on measurement, not faith: on questions the generator never
        anticipated it puts the right page in its top-10 **90.7%** of the time (run
        `libkb probe-recall`), even though its top-1 is only 39.3%. A bad oracle; a good sieve.

        And it is a HINT, NEVER A GATE (§7.4). A shortlist the librarian cannot escape is
        `open_book` all over again — and 9.3% of the time it would have deleted the answer from the
        universe. So the escape hatch (`open_book`) is offered in the same breath, and it works.
        """
        shortlist = self._shortlist({e.page_id for _, e in pairs})
        if not shortlist:
            # no catalog (or the embed failed) — fall back to the book gate, and say so plainly
            event = NavEvent(
                "shelf", meta.title, "shelf", shelf_id, "done", detail=f"{why}; book-by-book"
            )
            text = (
                f"This shelf holds {len(pairs)} pages across {len(books)} books — too many to lay "
                'out at once, and the card catalog is unavailable. Use open_book("<exact book '
                'title>") to open one book instead.\n\n' + self._render_menu(shelf_id)
            )
            return ToolOutcome(text=text, event=event)

        by_page = {e.page_id: (b, e) for b, e in pairs}
        self.state.current_toc = {}
        lines = [
            f"You are in: {self.store.path_str(shelf_id)}  [shelf]",
            f"\nThis shelf holds {len(pairs)} pages across {len(books)} books — too many to lay "
            "out at once.",
            f"\nThe card catalog ranked them against your question. The closest {len(shortlist)}:",
        ]
        for hit in shortlist:
            book, entry = by_page[hit.page_id]
            self.state.current_toc[entry.title.lower()] = entry
            row = f'  - "{entry.title}"'
            spine = _spine(entry.one_line, self.s.max_one_line_chars)
            if spine:
                row += f" — {spine}"
            lines.append(f'{row}   [from "{book.title}"]')
        lines.append(
            f"\nThere are {len(pairs) - len(shortlist)} more pages on this shelf. The catalog is a "
            "suggestion, not a verdict — if none of these is right, "
            'open_book("<exact book title>") to see any book in full:'
        )
        lines.append("  " + " · ".join(f'"{b.title}"' for b in books))
        lines.append('\nUse read_page("<title>") to read one of the pages above.')

        self.state.open_book_id = None
        self.state.visited.add(shelf_id)
        event = NavEvent(
            "shelf",
            meta.title,
            "shelf",
            shelf_id,
            "done",
            detail=f"{why}; catalog shortlisted {len(shortlist)} of {len(pairs)}",
        )
        return ToolOutcome(text="\n".join(lines), event=event)

    def _shortlist(self, page_ids: set[str]) -> list:
        """Rank this shelf's pages against the reader's question. One embed call, no gate.

        DENSE ONLY by default. §7.3 predicted a hybrid (dense + BM25) would win here, on the
        well-established grounds that embeddings miss rare terms. MEASURED, it loses — badly, on
        both query distributions, at every fusion weight (D-032). Kept behind `hybrid_shortlist`
        rather than deleted, because the rare-term mechanism is real; it just is not what this
        corpus's queries are made of.
        """
        if self.catalog is None or self.llm is None or not self.query:
            return []
        from libkb.catalog.search import hybrid_lookup, lookup

        search = hybrid_lookup if self.s.hybrid_shortlist else lookup
        try:
            return search(
                self.catalog,
                self.query,
                llm=self.llm,
                top_k=self.s.shelf_shortlist_k,
                within=page_ids,
            )
        except Exception:  # a flaky embed must degrade to the book gate, never break the walk
            return []

    def _crosslinks(self, books: list[NodeCard]) -> list[tuple[TOCEntry, str]]:
        """The see_also edges hanging off the books on this shelf, resolved to readable TOC entries.

        Only pages count: a see_also may point at any node, but only a page can be `read_page`d, and
        offering a link the librarian cannot follow is worse than offering none.
        """
        out: list[tuple[TOCEntry, str]] = []
        seen: set[NodeID] = set()
        for book in books:
            for sa in self.store.get(book.id).see_also:
                target = sa.target
                if target.kind != "page" or target.id in seen:
                    continue
                seen.add(target.id)
                try:
                    entry = self.store.toc_entry(target.id)
                    # the page's BOOK, not the page: repeating the title we just printed is waste
                    home = self.store.path_str(self.store.get(target.id).parent_id or target.id)
                except NodeNotFound:
                    continue  # a stale link (page moved or removed) must never break a menu
                out.append((entry, home))
        return out

    # -------------------------------------------------------------- dispatch

    def execute(self, name: str, args: dict) -> ToolOutcome:
        handler = {
            "browse": self._browse,
            "open_book": self._open_book,  # in shelf mode this is a deprecated alias for open_shelf
            "open_shelf": self._open_shelf,
            "read_page": self._read_page,
            "go_back": self._go_back,
            "found": self._found,
            "not_found": self._not_found,
            "ask_librarian": self._ask_librarian,
            "reframe": self._reframe,
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

    def _open_shelf(self, args: dict) -> ToolOutcome:
        shelf_id = self.state.cursor
        if self.store.get(shelf_id).kind != "shelf":
            return ToolOutcome(
                text="open_shelf() only works while you are standing on a shelf — "
                "browse(<shelf title>) into one first."
            )
        if self.state.hops + 1 > self.s.max_hops:
            return self._budget_exhausted()
        self.state.hops += 1
        return self._render_shelf(shelf_id)

    def _open_book(self, args: dict) -> ToolOutcome:
        # In shelf mode open_book is normally a no-op alias: the agent must not commit to a book,
        # and the whole shelf already contains what it was reaching for.
        #
        # EXCEPT on a shelf too wide to lay out. There, open_shelf returns a catalog SHORTLIST — and
        # if open_book still aliased to it, the librarian could never get past that shortlist. The
        # shortlist would become a gate, which is the exact sin of §7.4 (and of open_book itself).
        # So on a too-wide shelf, open_book means what it says: it really opens the book. That IS
        # the escape hatch.
        if self.s.routing_mode == "shelf" and not self._shelf_over_budget():
            outcome = self._open_shelf({})
            aimed = args.get("title", "").strip()
            if aimed and outcome.event is not None:
                prefix = (
                    f"(You do not need to pick a book. Here is the whole shelf — the pages of "
                    f'"{aimed}" are grouped under it.)\n\n'
                )
                return ToolOutcome(
                    text=prefix + outcome.text, event=outcome.event, terminal=outcome.terminal
                )
            return outcome

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
        entry = self._fuzzy_toc(title)
        if entry is None:
            if not self.state.current_toc:
                hint = (
                    "Nothing is laid out yet. Use open_shelf() first."
                    if self.s.routing_mode == "shelf"
                    else "No book is open. Use open_book(title) first."
                )
                return ToolOutcome(text=hint)
            return ToolOutcome(text=self._not_here(title, expected="page"))

        # Re-reading a page the librarian already has is FREE, and deliberately so. The digest (§6)
        # takes a page's full text out of the conversation once he walks on — so he must be able to
        # get it back, or the digest becomes a trap. But a re-read must not (a) burn a slot of the
        # page budget, which would push a walk into "budget reached" for consulting evidence it
        # already holds, nor (b) hand `compose_answer` the same page twice as if it were two
        # independent sources.
        already = next((p for p in self.state.pages if p.page_id == entry.page_id), None)
        if already is not None:
            path = self.store.path_str(already.page_id)
            return ToolOutcome(
                text=f"[PAGE — {path}]\n(you have read this page; here it is again in full)\n"
                f"<<<\n{already.markdown}\n>>>",
                digest=_digest(path, entry.one_line, already.markdown, self.s.max_one_line_chars),
            )

        if self.state.pages_read >= self.s.max_pages_per_nav:
            return ToolOutcome(
                text="Page budget reached — conclude now with found() or not_found()."
            )
        page = self.store.page(entry.page_id)
        self.state.pages.append(page)
        self.state.pages_read += 1
        path = self.store.path_str(page.page_id)
        block = f"[PAGE — {path}]\n<<<\n{page.markdown}\n>>>"
        event = NavEvent(
            "read",
            page.title,
            "page",
            page.page_id,
            "read",
            snippet=one_line_of(page.markdown, 120),
        )
        return ToolOutcome(
            text=block,
            event=event,
            digest=_digest(path, entry.one_line, page.markdown, self.s.max_one_line_chars),
        )

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

    def _reframe(self, args: dict) -> ToolOutcome:
        """Let the query evolve as the walk teaches the librarian the library's vocabulary (§8.3).

        Costs no hop: rewording is not travel. The pair (reader's words → library's words) is logged
        on the trajectory, and it is exactly the entry-vocabulary training data §8.2 wants — earned
        from real behaviour instead of guessed at ingest time.
        """
        new_query = args.get("new_query", "").strip()
        if not new_query:
            return ToolOutcome(text="Give the restated question.")
        if self.state.reframes >= self.s.max_reframes:
            return ToolOutcome(text="Reframe budget reached — search with the words you have.")
        self.state.reframes += 1
        old = self.query
        self.query = new_query  # the shelf shortlist ranks against this from now on
        self.state.reframed_from.append(old)
        event = NavEvent(
            "reframe", new_query, None, None, "done", detail=args.get("why", ""), snippet=old
        )
        return ToolOutcome(
            text=f'Restated. You are now searching for: "{new_query}"\n'
            "The rooms you have already seen are unchanged — keep walking.",
            event=event,
        )

    def _ask_librarian(self, args: dict) -> ToolOutcome:
        query = args.get("query", "").strip()
        if self.catalog is None or self.llm is None:
            return ToolOutcome(text="The card catalog is unavailable here — keep walking.")
        if self.state.librarian_calls >= self.s.max_ask_librarian:
            return ToolOutcome(
                text="Card-catalog budget reached — decide from the rooms you've seen."
            )
        self.state.librarian_calls += 1
        from libkb.catalog.search import lookup

        hits = lookup(self.catalog, query, llm=self.llm, top_k=self.s.catalog_top_k)
        if not hits:
            event = NavEvent("ask", query, None, None, "done", detail="no matches")
            return ToolOutcome(text="The catalog found no matching pages.", event=event)
        lines = ["The card catalog suggests these pages — walk to one and verify:"]
        lines += [f'  - {h.path}   (matched: "{h.text}")' for h in hits]
        event = NavEvent("ask", query, None, None, "done", detail=f"{len(hits)} suggestions")
        return ToolOutcome(text="\n".join(lines), event=event)

    # --------------------------------------------------------------- helpers

    def _resolve_child(self, title: str) -> NodeCard | None:
        return _best_match(title, self.state.current_children)

    def _fuzzy_toc(self, title: str) -> TOCEntry | None:
        return _best_match(title, self.state.current_toc)

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
        # Never throw away evidence already read. A long thrashing walk that DID read the right
        # page and then ran out of hops used to report NOT_FOUND and discard it — the answerer's
        # `sufficient` flag (P6) is what decides, not the hop counter.
        if self.state.pages:
            terminal = Terminal(
                status="FOUND",
                page_ids=[p.page_id for p in self.state.pages],
                reason="hop budget exhausted — answering from the pages already read",
            )
        else:
            terminal = Terminal(status="NOT_FOUND", reason="hop budget exhausted")
        return ToolOutcome(text="Hop budget exhausted.", event=event, terminal=terminal)


_MATCH_FLOOR = 0.6


def _spine(text: str, limit: int) -> str:
    """A menu label is a SPINE, not an abstract — cap it here and never trust what was stored.

    The folder import wrote whole frontmatter `description:` fields into `one_line` (measured on the
    live library: median 1013 chars). Capping at render fixes every existing menu without a
    migration, and holds even if some future ingest path regresses (ROUTING_REDESIGN §0a).
    """
    return one_line_of(text, limit) if text else ""


_DIGEST_SENTENCES = 2
_SENTENCE_END = re.compile(r"(?<=[.!?。？！])\s+")


def _digest(path: str, one_line: str, markdown: str, limit: int) -> str:
    """What the librarian keeps of a page once he has walked on (§6). NO LLM call — a digest that
    costs a round-trip would defeat its own purpose.

    It must still support the one judgement the navigator makes with it: *do I have enough to call
    found()?* A bare path cannot; a gist can. The full text is not lost — it lives in NavState.pages
    and is what `compose_answer` actually reads.
    """
    body = _SENTENCE_END.split(_strip_headings(markdown))
    gist = " ".join(s.strip() for s in body[:_DIGEST_SENTENCES] if s.strip())
    spine = _spine(one_line, limit)
    summary = f"{spine} {gist}".strip() if spine else gist
    return (
        f"[PAGE — {path}]\n"
        f"(read — the full text is retained as evidence; this is the gist)\n"
        f"{one_line_of(summary, 400)}"
    )


def _strip_headings(markdown: str) -> str:
    lines = [ln for ln in markdown.splitlines() if not ln.lstrip().startswith("#")]
    return " ".join(ln.strip() for ln in lines if ln.strip())


def _estimate_tokens(text: str) -> int:
    """Rough token count for budgeting a menu. ~4 chars/token — deliberately not a tokenizer call:
    this is a guard rail, and being 20% off does not change any decision it gates."""
    return len(text) // 4


def _best_match(title: str, options: dict[str, Any]) -> Any | None:
    """Resolve a model-supplied title to an option: exact → prefix → best difflib ratio.

    The old rule was `key in name or name in key`, first hit wins — so a short title like "RAG"
    matched any sibling merely containing it, and the winner was dict insertion order rather than
    similarity. Now the BEST scorer wins, and nothing below the floor matches at all.
    """
    key = title.lower().strip()
    if not key or not options:
        return None
    exact = options.get(key)
    if exact is not None:
        return exact
    best: Any | None = None
    best_score = 0.0
    for name, value in options.items():
        if name.startswith(key) or key.startswith(name):
            score = 0.95
        else:
            score = SequenceMatcher(None, key, name).ratio()
        if score > best_score:
            best, best_score = value, score
    return best if best_score >= _MATCH_FLOOR else None
