"""Deterministically map a source folder onto a DraftTree (see docs/INGEST.md §2-3).

No LLM. Extracts the levels the folder provides; marks the rest missing.
"""

from __future__ import annotations

import re
from pathlib import Path

from libkb.config import get_settings
from libkb.exceptions import IngestError
from libkb.ingest.frontmatter import first_heading, split_frontmatter
from libkb.ingest.models import DraftBook, DraftPage, DraftTree
from libkb.ingest.split import bound_page, is_apparatus
from libkb.library.models import one_line_of

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


def _first_of(front: dict, keys: tuple[str, ...]) -> object:
    """Frontmatter is a SHORTCUT, not a dependency.

    Every corpus names the same field differently — retail wrote `description:`, the AI-news corpus
    writes `summary:`, a raw PDF writes nothing. Growing a per-corpus branch for each of them is how
    an ingest stops being a product and becomes a pile of exceptions. So: harvest the standard names
    (this list is a vocabulary, not a special case), and where a page still comes up empty, the
    indexing call GENERATES the field for free (ingest/questions.py). No source ever needs code.
    """
    for key in keys:
        value = front.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


_DESC_KEYS = ("one_line", "description", "summary", "abstract", "tldr", "excerpt", "subtitle")
_KEYWORD_KEYS = ("keywords", "tags", "related_kpis", "topics", "entities")


def _pages_from_md(md: Path, root: Path) -> list[DraftPage]:
    """One file is USUALLY one page — but not by decree.

    A file is a unit the author chose for writing, not necessarily a unit that answers a question.
    The same budget that bounds a page split out of a PDF bounds a page imported from a folder, or
    the rule is not a rule, it is an exception with a nice name. A file within budget passes through
    untouched (which is every page of both corpora we have); an oversized one is cut by the same
    recursive structure-first rule (ingest/split.py).

    When a file DOES split, its frontmatter summary is deliberately NOT copied onto every fragment:
    the file's abstract describes the file, so stamping it on five sub-pages would make five pages
    look identical to the sieve. They are left empty and the indexing call writes each one a spine
    label of its own — which is exactly the discrimination the sieve needs.
    """
    page = _page_from_md(md, root)
    settings = get_settings()
    pieces = bound_page(
        page.body_markdown,
        page.title,
        max_tokens=settings.split_max_page_tokens,
        min_chars=settings.split_min_page_chars,
    )
    if len(pieces) < 2:
        page.indexable = not is_apparatus(page.title)
        return [page]
    return [
        DraftPage(
            title=_qualify(page.title, sub_title, i),
            body_markdown=body.strip(),
            source_ref=page.source_ref,
            indexable=not is_apparatus(sub_title),
        )
        for i, (sub_title, body) in enumerate(pieces)
        if body.strip()
    ]


def _qualify(page_title: str, sub_title: str, i: int) -> str:
    """Name a fragment after its file — but only ONCE.

    `split.py`'s size-splitter already names its slices `<title> (1/5)`, so blindly prefixing the
    file's title again produced `Attorney general … — Attorney general … (1/5)`: the title twice,
    250+ characters, and a filename Windows refuses to create (a real crash, on this corpus).
    """
    if not sub_title:
        return f"{page_title} ({i + 1})"
    if sub_title.startswith(page_title):  # the splitter already named it after the file
        return sub_title
    return f"{page_title} — {sub_title}"


def _page_from_md(md: Path, root: Path) -> DraftPage:
    text = md.read_text(encoding="utf-8", errors="replace")
    front, body = split_frontmatter(text)
    title = str(front.get("title") or first_heading(body) or humanize(md.stem)).strip()
    # A frontmatter `description:`/`summary:` is an abstract; a one_line is a SPINE LABEL. Copying
    # the former verbatim is what put 1000-char "one lines" in the live TOCs (ROUTING_REDESIGN §0a),
    # so it is capped here — and if it is empty, the LLM writes a real spine label at index time.
    raw = _first_of(front, _DESC_KEYS)
    raw_desc = str(raw or "").strip().replace("\n", " ")
    one_line = one_line_of(raw_desc, get_settings().max_one_line_chars)
    kws = _first_of(front, _KEYWORD_KEYS) or []
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
        page
        for md in sorted(topic.glob("*.md"), key=lambda p: p.name.lower())
        for page in _pages_from_md(md, root)
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
