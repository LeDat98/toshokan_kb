"""Split a parsed document into a DraftBook of pages (see docs/INGEST.md §11, P2b).

Structure-aware and deterministic: split on the shallowest repeated heading level. When a
document has no usable headings, fall back to size-based sectioning. (LLM page-titling of truly
unstructured docs is a future refinement.)
"""

from __future__ import annotations

import re

from libkb.ingest.models import DraftBook, DraftPage
from libkb.ingest.parse import ParsedDoc

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
_MIN_SECTION_CHARS = 40  # merge near-empty sections (a bare heading) into the previous one
_TARGET_CHARS = 2400  # size-split target when there are no headings
_MAX_PAGES = 80


def split_document(doc: ParsedDoc) -> DraftBook:
    sections = _heading_sections(doc.markdown)
    if len(sections) < 2:
        sections = _size_sections(doc.markdown)
    sections = _merge_tiny(sections)[:_MAX_PAGES]

    pages = [
        DraftPage(
            title=title,
            body_markdown=body.strip(),
            one_line=_first_sentence(body),
            source_ref=doc.source_ref,
        )
        for title, body in sections
        if body.strip()
    ]
    if not pages:  # a doc with content but no splittable body → one page
        pages = [
            DraftPage(
                title=doc.title, body_markdown=doc.markdown.strip(), source_ref=doc.source_ref
            )
        ]
    return DraftBook(title=doc.title, pages=pages, source_ref=doc.source_ref)


def _heading_sections(markdown: str) -> list[tuple[str, str]]:
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
            headings.append((i, len(m.group(1)), m.group(2).strip()))
    if not headings:
        return []

    # choose the shallowest level that repeats; else the shallowest present
    levels = [lv for _, lv, _ in headings]
    boundary = next((lv for lv in sorted(set(levels)) if levels.count(lv) >= 2), min(levels))
    bounds = [(i, text) for i, lv, text in headings if lv == boundary]

    sections: list[tuple[str, str]] = []
    preamble = "\n".join(lines[: bounds[0][0]]).strip()
    if preamble:
        sections.append(("Overview", preamble))
    for idx, (line_i, text) in enumerate(bounds):
        end = bounds[idx + 1][0] if idx + 1 < len(bounds) else len(lines)
        body = "\n".join(lines[line_i:end]).strip()
        sections.append((text, body))
    return sections


def _size_sections(markdown: str) -> list[tuple[str, str]]:
    paras = [p for p in re.split(r"\n\s*\n", markdown) if p.strip()]
    sections: list[tuple[str, str]] = []
    buf: list[str] = []
    size = 0
    for para in paras:
        buf.append(para)
        size += len(para)
        if size >= _TARGET_CHARS:
            sections.append(("", "\n\n".join(buf)))
            buf, size = [], 0
    if buf:
        sections.append(("", "\n\n".join(buf)))
    return [(title or f"Part {i + 1}", body) for i, (title, body) in enumerate(sections)]


def _merge_tiny(sections: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: list[list[str]] = []
    for title, body in sections:
        if merged and len(body) < _MIN_SECTION_CHARS:
            merged[-1][1] += "\n\n" + body
        else:
            merged.append([title, body])
    return [(t, b) for t, b in merged]


def _first_sentence(body: str, limit: int = 160) -> str:
    text = re.sub(r"^#{1,6}\s+.*$", "", body, count=1, flags=re.MULTILINE).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""
    cut = text[:limit]
    dot = cut.rfind(". ")
    return (cut[: dot + 1] if dot > 40 else cut).strip()
