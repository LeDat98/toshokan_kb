"""Materialized-view descriptions (principle P1).

Every non-leaf description is regenerated from its children, never hand-patched. This is
the ONLY module (besides store internals) permitted to call `store.set_description`
(enforced by tests/test_conventions.py).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from libkb.config import get_settings
from libkb.library.models import ROOT_ID, NodeID, one_line_of
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)


def _spine(text: str) -> str:
    """Same cap as the navigator's menus — a child's one_line is a label, not an abstract. Without
    it a book's description prompt carries ~1000 chars per page (ROUTING_REDESIGN §0a)."""
    return one_line_of(text, get_settings().max_one_line_chars) if text else ""


@dataclass
class RebuildReport:
    rebuilt: int = 0
    touched: list[NodeID] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.touched is None:
            self.touched = []


def rebuild_description(
    store: LibraryStore, node_id: NodeID, *, llm: LLM | None = None
) -> str | None:
    """Regenerate a node's description from its children — containers from their sub-nodes,
    a book from its pages (the TOC one-liners). Only leaf pages are left unchanged."""
    llm = llm or get_llm()
    meta = store.get(node_id)
    if meta.kind not in ("root", "domain", "shelf", "book"):
        return None
    children = store.children(node_id)
    if not children:
        return None

    child_lines = "\n".join(
        f'- "{c.title}" [{c.kind}]' + (f": {_spine(c.one_line)}" if c.one_line else "")
        for c in children
    )
    siblings = _sibling_lines(store, node_id)
    prompt = llm.load_prompt(
        "rebuild_description",
        title=meta.title,
        kind=meta.kind,
        children=child_lines,
        siblings=siblings or "(none)",
    )
    text = (llm.generate(prompt, temperature=0.2).text or "").strip()
    if not text:
        return None
    store.set_description(node_id, text, meta.description_rev + 1)
    log.info("description_rebuilt", node=node_id, kind=meta.kind, rev=meta.description_rev + 1)
    return text


def propagate_up(
    store: LibraryStore, node_id: NodeID, *, llm: LLM | None = None
) -> list[NodeID]:
    """Rebuild the chain of ancestor descriptions from a node up to the root."""
    llm = llm or get_llm()
    touched: list[NodeID] = []
    current: NodeID | None = node_id
    while current is not None:
        meta = store.get(current)
        if meta.kind in ("root", "domain", "shelf", "book") and rebuild_description(
            store, current, llm=llm
        ):
            touched.append(current)
        current = meta.parent_id
    return touched


def rebuild_all(
    store: LibraryStore, root_id: NodeID = ROOT_ID, *, llm: LLM | None = None
) -> RebuildReport:
    """Bottom-up full re-derivation (disaster recovery). Children before parents."""
    llm = llm or get_llm()
    report = RebuildReport()

    def visit(node_id: NodeID) -> None:
        meta = store.get(node_id)
        if meta.kind == "page":
            return
        for card in store.children(node_id):
            if card.kind != "page":
                visit(card.id)
        if meta.kind in ("root", "domain", "shelf", "book") and rebuild_description(
            store, node_id, llm=llm
        ):
            report.rebuilt += 1
            report.touched.append(node_id)

    visit(root_id)
    return report


def _sibling_lines(store: LibraryStore, node_id: NodeID) -> str:
    meta = store.get(node_id)
    if meta.parent_id is None:
        return ""
    siblings = [c for c in store.children(meta.parent_id) if c.id != node_id]
    return "\n".join(
        f'- "{c.title}"' + (f": {_spine(c.one_line)}" if c.one_line else "") for c in siblings
    )
