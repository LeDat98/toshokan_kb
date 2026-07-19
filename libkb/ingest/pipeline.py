"""Ingest one document end-to-end (see docs/INGEST.md §1, P2b).

parse → split → classify → file. Confident placements are filed into the tree; low-confidence
ones are parked under `_uncatalogued` for human review (principle P10). Reuses the DraftBook +
get_or_create commit from P2a.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from libkb.catalog.store import Catalog
from libkb.config import get_settings
from libkb.ingest.classify import Placement, classify_placement
from libkb.ingest.importer import get_or_create, index_page_safe
from libkb.ingest.parse import parse_source
from libkb.ingest.questions import index_page
from libkb.ingest.split import split_document
from libkb.library.models import ROOT_ID, UNCATALOGUED_ID, NodeID
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)

_PROPOSAL_RE = re.compile(r"\[proposed (.+?) ▸ (.+?) · conf ([\d.]+)\]")


@dataclass
class IngestEvent:
    stage: str  # parse | split | classify | file
    status: str  # running | done | gated | failed
    detail: str = ""


@dataclass
class IngestOutcome:
    status: str  # filed | uncatalogued
    book_id: NodeID
    book_path: str
    n_pages: int
    gated: bool
    placement: Placement
    source_type: str = ""
    source_ref: str = ""
    events: list[IngestEvent] = field(default_factory=list)


EventCB = Callable[[IngestEvent], None]


def ingest_document(
    source: str | Path,
    store: LibraryStore,
    *,
    gate: float | None = None,
    replace: bool = False,
    llm: LLM | None = None,
    catalog: Catalog | None = None,
    event_cb: EventCB | None = None,
) -> IngestOutcome:
    settings = get_settings()
    gate = settings.ingest_confidence_gate if gate is None else gate
    # only filed (non-gated) pages get indexed; parked ones wait for review/approval
    index_llm = (llm or get_llm()) if catalog is not None else None
    events: list[IngestEvent] = []

    def emit(stage: str, status: str, detail: str = "") -> None:
        ev = IngestEvent(stage, status, detail)
        events.append(ev)
        if event_cb:
            event_cb(ev)

    emit("parse", "running")
    doc = parse_source(source)
    emit("parse", "done", f"{doc.source_type}: {doc.title}")

    emit("split", "running")
    book = split_document(doc)
    emit("split", "done", f"{len(book.pages)} pages")

    emit("classify", "running")
    placement = classify_placement(book, store, llm=llm)
    gated = placement.confidence < gate
    emit(
        "classify",
        "gated" if gated else "done",
        f"{placement.path} · conf {placement.confidence:.2f}",
    )

    emit("file", "running")
    if gated:
        book.description = (
            f"[proposed {placement.path} · conf {placement.confidence:.2f}] {placement.rationale}"
        )
        bk = get_or_create(store, UNCATALOGUED_ID, "book", book.title, book.description)
    else:
        domain = get_or_create(store, ROOT_ID, "domain", placement.domain_title, "")
        shelf = get_or_create(store, domain.id, "shelf", placement.shelf_title, "")
        bk = get_or_create(
            store, shelf.id, "book", book.title, book.description or _fallback_desc(book)
        )

    existing = {c.title.strip().lower() for c in store.children(bk.id)}
    n = 0
    for page in book.pages:
        if page.title.strip().lower() in existing and not replace:
            continue
        pm = store.write_page(
            bk.id,
            page.title,
            page.body_markdown,
            one_line=page.one_line,
            keywords=page.keywords,
            source_ref=page.source_ref,
            indexable=page.indexable,
        )
        n += 1
        if not gated:
            index_page_safe(catalog, index_llm, store, pm.id, bk.id, page, book.title)
    store.recompute_stats(ROOT_ID)
    emit("file", "done", store.path_str(bk.id))

    return IngestOutcome(
        status="uncatalogued" if gated else "filed",
        book_id=bk.id,
        book_path=store.path_str(bk.id),
        n_pages=n,
        gated=gated,
        placement=placement,
        source_type=doc.source_type,
        source_ref=doc.source_ref,
        events=events,
    )


def list_uncatalogued(store: LibraryStore) -> list[dict]:
    """The review queue: books parked under _uncatalogued with their proposed placement."""
    rows: list[dict] = []
    for card in store.children(UNCATALOGUED_ID):
        if card.kind != "book":
            continue
        meta = store.get(card.id)
        m = _PROPOSAL_RE.search(meta.description or "")
        rows.append(
            {
                "id": card.id,
                "title": card.title,
                "n_pages": meta.stats.n_pages,
                "proposed_domain": m.group(1) if m else "",
                "proposed_shelf": m.group(2) if m else "",
                "confidence": float(m.group(3)) if m else None,
                "rationale": _PROPOSAL_RE.sub("", meta.description or "").strip(),
            }
        )
    return rows


def approve_placement(
    store: LibraryStore,
    book_id: NodeID,
    domain_title: str,
    shelf_title: str,
    *,
    catalog: Catalog | None = None,
    llm: LLM | None = None,
) -> str:
    """Move an uncatalogued book to an approved domain/shelf (creating them if needed).

    Pass `catalog` to index the now-approved pages into the flywheel (they were skipped at
    ingest time because the book was parked)."""
    domain = get_or_create(store, ROOT_ID, "domain", domain_title, "")
    shelf = get_or_create(store, domain.id, "shelf", shelf_title, "")
    store.move(book_id, shelf.id)
    store.recompute_stats(ROOT_ID)
    if catalog is not None:
        _index_book_pages(store, book_id, catalog, llm or get_llm())
    return store.path_str(book_id)


def _index_book_pages(store: LibraryStore, book_id: NodeID, catalog: Catalog, llm: LLM) -> int:
    book_title = store.get(book_id).title
    total = 0
    for child in store.children(book_id):
        if child.kind != "page":
            continue
        page = store.page(child.id)
        if not page.indexable:  # back matter stays on the shelf, out of the sieve
            continue
        try:
            card = index_page(
                catalog,
                page_id=page.page_id,
                book_id=book_id,
                path=store.path_str(page.page_id),
                title=page.title,
                markdown=page.markdown,
                book_title=book_title,
                llm=llm,
            )
        except Exception as exc:  # best-effort, per page
            log.warning("index_page_failed", page=page.page_id, error=str(exc))
            continue
        total += card.indexed_rows  # rows actually written — a text index writes rows, no questions
        entry = store.toc_entry(page.page_id)
        if not entry.one_line and card.one_line:
            store.set_toc_entry(
                page.page_id, one_line=card.one_line, keywords=card.keywords or None
            )
    return total


def _fallback_desc(book) -> str:
    titles = [p.title for p in book.pages[:3]]
    more = "…" if len(book.pages) > 3 else ""
    return f"{len(book.pages)} sections: " + ", ".join(titles) + more
