"""Split a parsed document into a DraftBook of pages (see docs/INGEST.md §11, P2b).

Structure first, size as the backstop, and **recursion** as the rule that ties them together.

The old rule chose ONE heading level for the whole document and never looked again. MEASURED on the
live library, that produced:

    9,992 chars  `3 Methodology`   — with **12 unused sub-headings inside it**
   13,136 chars  `References`      — the largest page in the library, and not knowledge at all

Neither is a "PDF problem" or a "which chunker do I pick for this document" problem. Both are a
missing base case. A document and a page are the same object at two scales, so the cut is the same
cut, applied until it stops being needed:

    cut at the shallowest repeated heading level
      → a piece still over budget: cut IT at its own shallowest repeated level (recurse)
        → structure exhausted and still over budget: only now cut by size
    → a piece too small to stand alone: merge it into its neighbour

One rule, every source. A new document type adds no code — which is the whole point: a per-format
splitting policy is not a product, it is a pile of exceptions waiting to be maintained.

Budgets live in Settings so `libkb probe-granularity` can sweep them and MEASURE the answer instead
of us guessing it.
"""

from __future__ import annotations

import re

from libkb.config import get_settings
from libkb.ingest.frontmatter import clean_title
from libkb.ingest.models import DraftBook, DraftPage
from libkb.ingest.parse import ParsedDoc

# re-exported so `library/sections.py` (which splits a page by the same rule) keeps its import
__all__ = ["clean_title", "split_document", "split_into_pages", "bound_page", "is_apparatus"]

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")

# Back matter is not knowledge. A bibliography answers no question a reader will ask of the library,
# yet it was the single largest page we had — 13,136 chars, indexed, embedded, and eligible to be
# retrieved and read as "evidence". We keep it (it is part of the document, and a citation may want
# it) but it never enters the card catalog: `indexable=False`. Deliberately narrow — an APPENDIX is
# knowledge (ours hold training hyperparameters), and so is anything we are not sure about.
_APPARATUS_RE = re.compile(
    r"^\W*(?:\d+[.\s]*)?"
    r"(references?|bibliography|works\s+cited|acknowledge?ments?"
    r"|tài\s+liệu\s+tham\s+khảo|lời\s+cảm\s+ơn)"
    r"\W*$",
    re.IGNORECASE,
)

_TARGET_CHARS = 2400  # size-split target, used only where a document has no structure left
_MAX_PAGES = 80


def split_document(doc: ParsedDoc) -> DraftBook:
    """A DOCUMENT becomes a BOOK: its structure defines the pages."""
    settings = get_settings()
    pieces = split_into_pages(
        doc.markdown,
        doc_title=doc.title,
        max_tokens=settings.split_max_page_tokens,
        min_chars=settings.split_min_page_chars,
    )
    limit = settings.max_one_line_chars
    pages = [
        DraftPage(
            title=title or doc.title,
            body_markdown=body.strip(),
            one_line=_first_sentence(body, limit),
            source_ref=doc.source_ref,
            indexable=not is_apparatus(title),
        )
        for title, body in pieces[:_MAX_PAGES]
        if body.strip()
    ]
    if not pages:  # content, but nothing splittable → one page
        pages = [
            DraftPage(
                title=doc.title, body_markdown=doc.markdown.strip(), source_ref=doc.source_ref
            )
        ]
    return DraftBook(title=doc.title, pages=pages, source_ref=doc.source_ref)


def split_into_pages(
    markdown: str,
    *,
    doc_title: str = "",
    max_tokens: int = 2000,
    min_chars: int = 300,
) -> list[tuple[str, str]]:
    """Cut a DOCUMENT into pages. Its headings are its chapters, so the first cut always happens —
    a book with one page is not a book. Below that, size takes over: a chapter still over budget is
    cut again at its own shallowest repeated level, and only when the structure runs out does the
    size-splitter get a vote."""
    max_chars = max_tokens * 4  # same 4-chars-per-token estimate as library/sections.py
    sections = _heading_sections(markdown.strip(), doc_title=doc_title)
    if not sections:
        return bound_page(markdown, doc_title, max_tokens=max_tokens, min_chars=min_chars)
    leaves: list[tuple[str, str]] = []
    for title, body in sections:
        leaves += _cut(body, title=title, depth=1, max_chars=max_chars)
    return _merge_tiny(leaves, min_chars)


def bound_page(
    markdown: str, title: str = "", *, max_tokens: int = 2000, min_chars: int = 300
) -> list[tuple[str, str]]:
    """Bound a thing that is ALREADY a page — a file in an imported folder, say.

    Here the author has already chosen the leaf, and that choice is information: we do not overrule
    it because the file happens to have headings in it. Every page of both live corpora passes
    through untouched. Only an oversized page is cut, by exactly the same recursive rule — which is
    what makes this a budget and not a per-format policy.
    """
    max_chars = max_tokens * 4
    leaves = _cut(markdown.strip(), title=title, depth=0, max_chars=max_chars)
    return _merge_tiny(leaves, min_chars)


def is_apparatus(title: str) -> bool:
    """Back matter: part of the document, but never an answer. Kept, not indexed."""
    return bool(_APPARATUS_RE.match(clean_title(title)))


def _cut(body: str, *, title: str, depth: int, max_chars: int) -> list[tuple[str, str]]:
    """Recursive base case: a piece within budget is a leaf, whatever its structure.

    Back matter is also a base case, at any size. A 15,000-char bibliography is over budget, but
    cutting it into six pages buys nothing — nobody reads it and nothing indexes it, so the only
    effect would be six junk entries in the book's table of contents (and, because the size-splitter
    renames its pieces `… (3/6)`, six titles the apparatus filter no longer recognises — which is
    how the bibliography would have crept back into the catalog).
    """
    if len(body) <= max_chars or is_apparatus(title):
        return [(title, body)]

    sections = _heading_sections(body)
    if len(sections) < 2:
        # Structure exhausted and still over budget. ONLY here does size get a vote — and a
        # size-split is an admission of defeat, not a strategy.
        return _size_sections(body, title)

    out: list[tuple[str, str]] = []
    for sub_title, sub_body in sections:
        # At depth 0 a section title stands alone ("3 Methodology"). Deeper it needs its parent, or
        # the citation is ambiguous — half the sub-headings in a document are called "Overview".
        name = sub_title if depth == 0 or not title else f"{title} — {sub_title}"
        out += _cut(sub_body, title=name, depth=depth + 1, max_chars=max_chars)
    return out


def _heading_sections(markdown: str, doc_title: str = "") -> list[tuple[str, str]]:
    """Cut at the shallowest repeated heading level. The text above the first cut is a section too —
    it is where a document states its subject before drilling in."""
    lines = markdown.splitlines()
    headings: list[tuple[int, int, str]] = []  # (line_index, level, text)
    in_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if m:
            headings.append((i, len(m.group(1)), clean_title(m.group(2))))
    headings = _drop_furniture(headings, doc_title)
    if not headings:
        return []

    levels = [lv for _, lv, _ in headings]
    boundary = next((lv for lv in sorted(set(levels)) if levels.count(lv) >= 2), min(levels))
    bounds = [(i, text) for i, lv, text in headings if lv == boundary]

    sections: list[tuple[str, str]] = []
    preamble = "\n".join(lines[: bounds[0][0]]).strip()
    if preamble:
        # It gets qualified by its parent on the way up ("3 Methodology — Overview"), so a generic
        # name here is harmless and a specific one would just repeat the parent's.
        sections.append(("Overview", preamble))
    for idx, (line_i, text) in enumerate(bounds):
        end = bounds[idx + 1][0] if idx + 1 < len(bounds) else len(lines)
        chunk = "\n".join(lines[line_i:end]).strip()
        if chunk:
            sections.append((text, chunk))
    return sections


def _drop_furniture(
    headings: list[tuple[int, int, str]], doc_title: str
) -> list[tuple[int, int, str]]:
    """Not everything shaped like a heading is structure.

    Two things masquerade as chapters, and both are MEASURED on the live corpora, not imagined:

    **The document's own title.** A paper reprints its title in two languages, so `#` "repeats" and
    the splitter cheerfully makes each language a chapter — every one of the 37 resulting pages was
    then prefixed with a 70-character paper title. A document's title is what the BOOK is called; it
    is not one of the book's chapters.

    **A running header.** A PDF converter infers heading level from font size, so the title printed
    at the top of every physical page becomes a heading — 30 identical ones. Split on those and you
    get 30 pages with the same name (and, downstream, a slug collision). The tell is domination: a
    real heading that repeats (`Exercises` in each chapter of a textbook) is a small fraction of its
    level; furniture IS its level. Hence 4+ occurrences AND ≥40% of the level — a threshold that
    keeps the textbook and kills the running header.
    """
    title_key = clean_title(doc_title).strip().lower()
    kept = [h for h in headings if not (title_key and h[2].strip().lower() == title_key)]

    by_level: dict[int, list[str]] = {}
    for _, level, text in kept:
        by_level.setdefault(level, []).append(text.strip().lower())
    furniture = {
        text
        for level, texts in by_level.items()
        for text in set(texts)
        if texts.count(text) >= 4 and texts.count(text) >= 0.4 * len(texts)
    }
    return [h for h in kept if h[2].strip().lower() not in furniture]


def _size_sections(markdown: str, title: str) -> list[tuple[str, str]]:
    """Last resort: paragraph-packed slices. Never splits mid-paragraph."""
    paras = [p for p in re.split(r"\n\s*\n", markdown) if p.strip()]
    slices: list[str] = []
    buf: list[str] = []
    size = 0
    for para in paras:
        buf.append(para)
        size += len(para)
        if size >= _TARGET_CHARS:
            slices.append("\n\n".join(buf))
            buf, size = [], 0
    if buf:
        slices.append("\n\n".join(buf))
    if len(slices) < 2:
        return [(title, markdown)]
    stem = title or "Part"
    return [(f"{stem} ({i + 1}/{len(slices)})", body) for i, body in enumerate(slices)]


def _merge_tiny(leaves: list[tuple[str, str]], min_chars: int) -> list[tuple[str, str]]:
    """A leaf too small to stand alone is not a page; it is a stray heading. Fold it forward — but
    never fold back matter into knowledge, or the bibliography re-enters the catalog by the back
    door on the arm of the section above it."""
    merged: list[list[str]] = []
    for title, body in leaves:
        fold = (
            merged
            and len(body) < min_chars
            and not is_apparatus(title)
            and not is_apparatus(merged[-1][0])
        )
        if fold:
            merged[-1][1] += "\n\n" + body
        else:
            merged.append([title, body])
    return [(t, b) for t, b in merged]


def _first_sentence(body: str, limit: int = 120) -> str:
    text = re.sub(r"^#{1,6}\s+.*$", "", body, count=1, flags=re.MULTILINE).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""
    cut = text[:limit]
    dot = cut.rfind(". ")
    return (cut[: dot + 1] if dot > 40 else cut).strip()
