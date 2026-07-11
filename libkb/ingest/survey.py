"""Deterministically map a source folder onto a DraftTree (see docs/INGEST.md §2-3).

No LLM. Extracts the levels the folder provides; marks the rest missing.
"""

from __future__ import annotations

import re
from pathlib import Path

from libkb.exceptions import IngestError
from libkb.ingest.frontmatter import first_heading, split_frontmatter
from libkb.ingest.models import DraftBook, DraftPage, DraftTree

_PRIORITY_RE = re.compile(r"^(P\d)[_-]", re.IGNORECASE)
_MAX_KEYWORDS = 6


def humanize(name: str) -> str:
    """'P0_KPI_Dictionary' -> 'KPI Dictionary'; 'lead-time_impact' -> 'Lead Time Impact'."""
    name = _PRIORITY_RE.sub("", name)
    name = name.replace("_", " ").replace("-", " ")
    words = [w for w in name.split() if w]
    return " ".join(w if (w.isupper() and len(w) <= 4) else w.capitalize() for w in words)


def priority_of(name: str) -> str | None:
    m = _PRIORITY_RE.match(name)
    return m.group(1).upper() if m else None


def _has_md(folder: Path) -> bool:
    return any(folder.glob("*.md"))


def _subdirs(folder: Path) -> list[Path]:
    return sorted((p for p in folder.iterdir() if p.is_dir()), key=lambda p: p.name.lower())


def _page_from_md(md: Path, root: Path) -> DraftPage:
    text = md.read_text(encoding="utf-8", errors="replace")
    front, body = split_frontmatter(text)
    title = str(front.get("title") or first_heading(body) or humanize(md.stem)).strip()
    one_line = str(front.get("description") or "").strip().replace("\n", " ")
    kws = front.get("related_kpis") or front.get("keywords") or []
    if isinstance(kws, str):
        kws = [k.strip() for k in kws.split(",")]
    keywords = [str(k).strip() for k in kws if str(k).strip()][:_MAX_KEYWORDS]
    return DraftPage(
        title=title,
        body_markdown=body.strip(),
        one_line=one_line,
        keywords=keywords,
        source_ref=str(md.relative_to(root)).replace("\\", "/"),
    )


def _book_from_dir(topic: Path, root: Path) -> DraftBook | None:
    pages = [
        _page_from_md(md, root) for md in sorted(topic.glob("*.md"), key=lambda p: p.name.lower())
    ]
    if not pages:
        return None
    return DraftBook(
        title=humanize(topic.name),
        pages=pages,
        priority=priority_of(topic.name),
        source_ref=str(topic.relative_to(root)).replace("\\", "/"),
    )


def survey_folder(path: str | Path, domain: str) -> DraftTree:
    """Map a folder onto a DraftTree.

    Depth rule (docs/INGEST.md §3):
    - folder whose children are topic-folders of .md files  → each child = a BOOK, files = PAGES
      (shelf slot missing → resolver fills it).
    - a folder deeper (child folders themselves contain topic-folders) → child folders = SHELVES.
    """
    root = Path(path)
    if not root.is_dir():
        raise IngestError(f"not a folder: {root}")

    child_dirs = _subdirs(root)
    if not child_dirs and _has_md(root):
        # a single flat folder of .md files → one book named after the folder
        book = _book_from_dir(root, root)
        books = [book] if book else []
        return _tree(domain, books)

    # is there an extra container level? (grandchildren are folders with .md → children are shelves)
    shelfish = any(_subdirs(d) and not _has_md(d) for d in child_dirs)

    if shelfish:
        shelves = []
        for shelf_dir in child_dirs:
            shelf_books = [b for d in _subdirs(shelf_dir) if (b := _book_from_dir(d, root))]
            if shelf_books:
                from libkb.ingest.models import DraftShelf

                shelves.append(DraftShelf(title=humanize(shelf_dir.name), books=shelf_books))
        tree = DraftTree(domain_title=domain, shelves=shelves)
        tree.books = [b for sh in shelves for b in sh.books]
        tree.provided = {"shelf", "book", "page", "title"}
        tree.missing = set()
        return tree

    # flat: each child folder is a book; shelf level is missing
    books = [b for d in child_dirs if (b := _book_from_dir(d, root))]
    return _tree(domain, books)


def _tree(domain: str, books: list[DraftBook]) -> DraftTree:
    tree = DraftTree(domain_title=domain, books=books)
    provided = {"book", "page", "title"}
    if any(p.one_line for b in books for p in b.pages):
        provided.add("description")
    tree.provided = provided
    tree.missing = {"shelf"}  # domain supplied by the caller; shelf never in a flat folder
    return tree
