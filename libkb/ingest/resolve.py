"""Fill the missing shelf slot of a DraftTree (see docs/INGEST.md §8).

Strategies:
- "single"    one shelf holding every book (deterministic).
- "priority"  group by the P0/P1/P2 prefix the source encoded (deterministic).
- "auto"      an LLM proposes discriminative thematic shelves (needs an LLM).
"""

from __future__ import annotations

import structlog

from libkb.exceptions import IngestError
from libkb.ingest.models import DraftBook, DraftShelf, DraftTree
from libkb.llm.client import LLM

log = structlog.get_logger(__name__)

_GROUP_SCHEMA = {
    "type": "object",
    "properties": {
        "shelves": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "books": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "books"],
            },
        }
    },
    "required": ["shelves"],
}

_PRIORITY_NAMES = {"P0": "P0 — Core", "P1": "P1 — Extended", "P2": "P2 — Supplementary"}


def resolve_shelves(
    tree: DraftTree,
    strategy: str = "single",
    *,
    shelf_name: str = "General",
    llm: LLM | None = None,
) -> DraftTree:
    if tree.shelves:  # source already provided shelves (deep folder) — nothing to fill
        return tree
    if not tree.books:
        raise IngestError("nothing to import: the source produced no books")

    if strategy == "single":
        tree.shelves = [DraftShelf(title=shelf_name, books=list(tree.books))]
    elif strategy == "priority":
        tree.shelves = _by_priority(tree.books)
    elif strategy == "auto":
        if llm is None:
            raise IngestError("strategy 'auto' needs an LLM")
        tree.shelves = _auto_group(tree, llm)
    else:
        raise IngestError(f"unknown shelf strategy: {strategy}")

    tree.missing.discard("shelf")
    tree.provided.add("shelf")
    return tree


def _by_priority(books: list[DraftBook]) -> list[DraftShelf]:
    groups: dict[str, list[DraftBook]] = {}
    for book in books:
        groups.setdefault(book.priority or "P0", []).append(book)
    return [
        DraftShelf(title=_PRIORITY_NAMES.get(pri, pri), books=groups[pri]) for pri in sorted(groups)
    ]


def _auto_group(tree: DraftTree, llm: LLM) -> list[DraftShelf]:
    by_title = {b.title: b for b in tree.books}
    n = len(tree.books)
    listing = "\n".join(
        f'- "{b.title}" — {b.pages[0].one_line[:120] if b.pages else ""}' for b in tree.books
    )
    prompt = llm.load_prompt(
        "group_shelves",
        domain=tree.domain_title,
        books=listing,
        min_shelves=max(2, n // 6),
        max_shelves=max(3, min(6, n // 2)),
    )
    data = llm.generate_json(prompt, schema=_GROUP_SCHEMA)

    shelves: list[DraftShelf] = []
    assigned: set[str] = set()
    for item in data.get("shelves", []):
        members = [
            by_title[t] for t in item.get("books", []) if t in by_title and t not in assigned
        ]
        assigned.update(b.title for b in members)
        if members:
            shelves.append(
                DraftShelf(
                    title=item.get("title", "General").strip(),
                    description=item.get("description", "").strip(),
                    books=members,
                )
            )
    # safety net: any book the model dropped goes to a catch-all shelf
    leftover = [b for b in tree.books if b.title not in assigned]
    if leftover:
        log.warning("auto_group_leftover", count=len(leftover))
        shelves.append(DraftShelf(title="General", books=leftover))
    return shelves
