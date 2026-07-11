"""Commit a DraftTree into the LibraryStore, and the top-level import_folder entry point.

Copies content into the canonical library (docs/INGEST.md §6). Containers are get-or-created
by slug so re-imports are idempotent; existing pages are skipped unless `replace=True`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import structlog

from libkb.ingest.models import DraftBook, DraftTree, ImportReport
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
    progress: ProgressCB | None = None,
) -> ImportReport:
    """Survey → resolve shelves → commit. `strategy='auto'` needs `llm`."""

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
    return commit(tree, store, strategy=strategy, replace=replace, progress=progress)


def commit(
    tree: DraftTree,
    store: LibraryStore,
    *,
    strategy: str = "",
    replace: bool = False,
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
                store.write_page(
                    bk.id,
                    page.title,
                    page.body_markdown,
                    one_line=page.one_line,
                    keywords=page.keywords,
                    source_ref=page.source_ref,
                )
                report.pages += 1
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


def _book_description(book: DraftBook) -> str:
    """Deterministic fallback when no shelf/LLM description is available."""
    titles = [p.title for p in book.pages[:3]]
    more = "…" if len(book.pages) > 3 else ""
    return f"{len(book.pages)} topics: " + ", ".join(titles) + more
