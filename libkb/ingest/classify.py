"""Decide where a document belongs in the live tree (see docs/INGEST.md §9, P2b).

Top-down placement: pick an existing domain+shelf or propose new ones, with a confidence the
pipeline gates on. Reconciles the model's is-new flags against what actually exists.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from libkb.ingest.models import DraftBook
from libkb.library.models import ROOT_ID, UNCATALOGUED_ID, NodeID, slugify
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)

_SCHEMA = {
    "type": "object",
    "properties": {
        "domain_title": {"type": "string"},
        "domain_is_new": {"type": "boolean"},
        "shelf_title": {"type": "string"},
        "shelf_is_new": {"type": "boolean"},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["domain_title", "shelf_title", "confidence"],
}


@dataclass
class Placement:
    domain_title: str
    shelf_title: str
    confidence: float
    rationale: str = ""
    domain_is_new: bool = True
    shelf_is_new: bool = True
    domain_id: NodeID | None = None
    shelf_id: NodeID | None = None

    @property
    def path(self) -> str:
        return f"{self.domain_title} ▸ {self.shelf_title}"


def classify_placement(
    book: DraftBook, store: LibraryStore, *, llm: LLM | None = None
) -> Placement:
    llm = llm or get_llm()
    outline = "; ".join(p.title for p in book.pages[:12]) or book.title
    excerpt = (book.pages[0].body_markdown[:600] if book.pages else "").strip()
    prompt = llm.load_prompt(
        "classify_doc",
        tree=_tree_context(store),
        title=book.title,
        outline=outline,
        excerpt=excerpt or "(no excerpt)",
    )
    data = llm.generate_json(prompt, schema=_SCHEMA)

    placement = Placement(
        domain_title=str(data["domain_title"]).strip(),
        shelf_title=str(data["shelf_title"]).strip(),
        confidence=max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
        rationale=str(data.get("rationale", "")).strip(),
    )
    _reconcile(store, placement)
    log.info(
        "classified",
        path=placement.path,
        confidence=placement.confidence,
        domain_new=placement.domain_is_new,
        shelf_new=placement.shelf_is_new,
    )
    return placement


def _tree_context(store: LibraryStore) -> str:
    lines: list[str] = []
    for domain in store.children(ROOT_ID):
        if domain.id == UNCATALOGUED_ID or domain.kind != "domain":
            continue
        lines.append(f"- {domain.title} (domain)")
        for shelf in store.children(domain.id):
            if shelf.kind == "shelf":
                lines.append(f"    - {shelf.title} (shelf)")
    return "\n".join(lines) or "(the library is empty — propose a new domain)"


def _reconcile(store: LibraryStore, placement: Placement) -> None:
    """Trust reality over the model's flags: match titles to existing nodes by slug."""
    domain_slug = slugify(placement.domain_title)
    domain = next(
        (
            c
            for c in store.children(ROOT_ID)
            if c.kind == "domain" and slugify(c.title) == domain_slug
        ),
        None,
    )
    if domain is None:
        placement.domain_is_new = True
        placement.shelf_is_new = True
        return
    placement.domain_id = domain.id
    placement.domain_is_new = False

    shelf_slug = slugify(placement.shelf_title)
    shelf = next(
        (
            c
            for c in store.children(domain.id)
            if c.kind == "shelf" and slugify(c.title) == shelf_slug
        ),
        None,
    )
    if shelf is None:
        placement.shelf_is_new = True
    else:
        placement.shelf_id = shelf.id
        placement.shelf_is_new = False
