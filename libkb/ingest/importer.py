"""Commit a DraftTree into the LibraryStore, and the top-level import_folder entry point.

Copies content into the canonical library (docs/INGEST.md §6). Containers are get-or-created
by slug so re-imports are idempotent; existing pages are skipped unless `replace=True`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path

import structlog

from libkb.catalog.store import Catalog
from libkb.exceptions import NodeNotFound
from libkb.ingest.models import DraftBook, DraftPage, DraftTree, ImportReport
from libkb.ingest.questions import PageCard, index_page
from libkb.ingest.resolve import resolve_shelves
from libkb.ingest.survey import survey_folder
from libkb.library.models import ROOT_ID, NodeID, NodeKind, NodeMeta, slugify
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM

log = structlog.get_logger(__name__)

ProgressCB = Callable[[str], None]


def import_folder(
    path: str | Path,
    domain: str,
    store: LibraryStore,
    *,
    strategy: str = "single",
    shelf_name: str = "General",
    replace: bool = False,
    llm: LLM | None = None,
    catalog: Catalog | None = None,
    progress: ProgressCB | None = None,
) -> ImportReport:
    """Survey → resolve shelves → commit. `strategy='auto'` needs `llm`; pass `catalog`+`llm`
    to also index each page into the card catalog (the flywheel)."""

    def note(msg: str) -> None:
        if progress:
            progress(msg)

    note(f"surveying {path}")
    tree = survey_folder(path, domain)
    note(f"found {len(tree.books)} books, {tree.n_pages} pages; missing: {sorted(tree.missing)}")

    note(f"resolving shelves (strategy={strategy})")
    resolve_shelves(tree, strategy, shelf_name=shelf_name, llm=llm)
    note(f"→ {len(tree.shelves)} shelves")

    note("committing to the library")
    return commit(
        tree, store, strategy=strategy, replace=replace, llm=llm, catalog=catalog, progress=progress
    )


def commit(
    tree: DraftTree,
    store: LibraryStore,
    *,
    strategy: str = "",
    replace: bool = False,
    llm: LLM | None = None,
    catalog: Catalog | None = None,
    progress: ProgressCB | None = None,
) -> ImportReport:
    domain = get_or_create(store, ROOT_ID, "domain", tree.domain_title, tree.domain_description)
    report = ImportReport(
        domain=domain.title,
        shelf_strategy=strategy,
        provided=sorted(tree.provided),
        missing=sorted(tree.missing),
    )
    for shelf in tree.shelves:
        sh = get_or_create(store, domain.id, "shelf", shelf.title, shelf.description)
        report.shelves += 1
        for book in shelf.books:
            bk = get_or_create(
                store, sh.id, "book", book.title, book.description or _book_description(book)
            )
            report.books += 1
            existing = {c.title.strip().lower() for c in store.children(bk.id)}
            for page in book.pages:
                if page.title.strip().lower() in existing and not replace:
                    report.skipped_pages += 1
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
                report.pages += 1
                if index_page_safe(catalog, llm, store, pm.id, bk.id, page, book.title):
                    report.indexed_pages += 1
                elif catalog is not None and page.indexable:
                    # A page in the library but NOT in the catalog is invisible to the sieve, which
                    # means it may as well not exist. This used to be logged and forgotten: 439 of
                    # 2,079 pages were lost that way and the import still reported success.
                    report.index_failures.append(store.path_str(pm.id))
            report.paths.append(store.path_str(bk.id))
            if progress:
                progress(f"  filed {store.path_str(bk.id)}")
    store.recompute_stats(ROOT_ID)
    return report


def get_or_create(
    store: LibraryStore, parent_id: NodeID, kind: NodeKind, title: str, description: str
) -> NodeMeta:
    slug = slugify(title)
    for card in store.children(parent_id):
        if card.kind == kind and slugify(card.title) == slug:
            return store.get(card.id)
    return store.create(parent_id, kind, title, description)


def index_page_safe(
    catalog: Catalog | None,
    llm: LLM | None,
    store: LibraryStore,
    page_id: NodeID,
    book_id: NodeID,
    page: DraftPage,
    book_title: str,
) -> bool:
    """Best-effort flywheel: index one page, but never let indexing abort an import.

    Returns whether the page made it into the catalog — and the CALLER MUST LOOK. "Best-effort"
    was doing a lot of quiet work here: a per-page exception was logged and swallowed, so an import
    could lose a fifth of the corpus from the sieve and still print a success line. It did exactly
    that (439/2,079). Failure is now a return value, not a log entry nobody reads.

    Also where the ingest CONTRACT is closed: when the sieve indexes questions, the same call
    generated a spine label and keywords for free, so we file whatever the source left empty here. A
    text index generates neither — `fill_gaps` then fills nothing, and the page keeps the
    deterministic first-sentence `one_line` the splitter gave it. Either way a page's furniture does
    not depend on which folder it came from."""
    if catalog is None or llm is None or not page.indexable:
        return False
    try:
        card = index_page(
            catalog,
            page_id=page_id,
            book_id=book_id,
            path=store.path_str(page_id),
            title=page.title,
            markdown=page.body_markdown,
            book_title=book_title,
            llm=llm,
        )
    except Exception as exc:  # a flaky embed must not lose the import — but it must not hide either
        log.warning("index_page_failed", page=page_id, error=str(exc))
        return False
    fill_gaps(store, page_id, page, card)
    # success = rows actually entered the sieve, NOT "questions were generated" — a text index
    # generates no questions yet indexes the page (the 439/2,079 silent-loss guard survives that)
    return card.indexed_rows > 0


def fill_gaps(store: LibraryStore, page_id: NodeID, page: DraftPage, card: PageCard) -> None:
    """The source is a shortcut, never a dependency: fill only what it left empty."""
    one_line = card.one_line if not page.one_line else None
    keywords = card.keywords if not page.keywords else None
    if one_line or keywords:
        with contextlib.suppress(NodeNotFound):  # a page outside a TOC — nothing to fill
            store.set_toc_entry(page_id, one_line=one_line, keywords=keywords)


def _book_description(book: DraftBook) -> str:
    """Deterministic fallback when no shelf/LLM description is available."""
    titles = [p.title for p in book.pages[:3]]
    more = "…" if len(book.pages) > 3 else ""
    return f"{len(book.pages)} topics: " + ", ".join(titles) + more
