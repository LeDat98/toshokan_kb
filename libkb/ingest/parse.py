"""Turn a document source (file path or URL) into markdown (see docs/INGEST.md §11, P2b).

Parser deps (pymupdf4llm, trafilatura) are imported lazily so the package stays importable
without them and unit tests don't require them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
import structlog

from libkb.exceptions import IngestError
from libkb.ingest.frontmatter import clean_title, first_heading, split_frontmatter

log = structlog.get_logger(__name__)

_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
_HTML_SUFFIXES = {".html", ".htm"}


@dataclass
class ParsedDoc:
    title: str
    markdown: str
    source_ref: str
    source_type: str  # md | txt | pdf | html | url


def parse_source(source: str | Path) -> ParsedDoc:
    """Dispatch on a URL or a file suffix."""
    text = str(source)
    if text.startswith(("http://", "https://")):
        return _parse_url(text)
    path = Path(source)
    if not path.is_file():
        raise IngestError(f"not a file or URL: {source}")
    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        return _parse_text(path)
    if suffix == ".pdf":
        return _parse_pdf(path)
    if suffix in _HTML_SUFFIXES:
        return _parse_html_file(path)
    raise IngestError(f"unsupported document type: {suffix or '(no extension)'}")


def _title_from(markdown: str, fallback: str) -> str:
    # clean_title here so the DOCUMENT title (which becomes the book name) is stripped of markdown
    # emphasis too, not just the section headings — a book was named `**PDF …**` because this funnel
    # was the one place clean_title had been missing.
    return clean_title(first_heading(markdown) or fallback)


def _parse_text(path: Path) -> ParsedDoc:
    raw = path.read_text(encoding="utf-8", errors="replace")
    front, body = split_frontmatter(raw)
    title = str(front.get("title") or _title_from(body, path.stem))
    kind = "md" if path.suffix.lower() != ".txt" else "txt"
    return ParsedDoc(title=title, markdown=body.strip(), source_ref=str(path), source_type=kind)


def _parse_pdf(path: Path) -> ParsedDoc:
    try:
        import pymupdf4llm
    except ImportError as exc:  # pragma: no cover - dep guard
        raise IngestError("PDF support needs pymupdf4llm (pip install pymupdf4llm)") from exc
    markdown = pymupdf4llm.to_markdown(str(path)).strip()
    if not markdown:
        raise IngestError(f"no extractable text in {path.name}")
    return ParsedDoc(
        title=_title_from(markdown, path.stem),
        markdown=markdown,
        source_ref=str(path),
        source_type="pdf",
    )


def _extract_html(html: str, source_ref: str, source_type: str) -> ParsedDoc:
    try:
        import trafilatura
    except ImportError as exc:  # pragma: no cover - dep guard
        raise IngestError("HTML support needs trafilatura (pip install trafilatura)") from exc
    markdown = trafilatura.extract(html, output_format="markdown", include_tables=True) or ""
    markdown = markdown.strip()
    if not markdown:
        raise IngestError(f"no main content extracted from {source_ref}")
    title = None
    meta = trafilatura.extract_metadata(html)
    if meta and meta.title:
        title = meta.title
    return ParsedDoc(
        title=(title or _title_from(markdown, source_ref)).strip(),
        markdown=markdown,
        source_ref=source_ref,
        source_type=source_type,
    )


def _parse_html_file(path: Path) -> ParsedDoc:
    return _extract_html(path.read_text(encoding="utf-8", errors="replace"), str(path), "html")


def _parse_url(url: str) -> ParsedDoc:
    try:
        resp = httpx.get(
            url, follow_redirects=True, timeout=30.0, headers={"User-Agent": "LibraryKB/0.1"}
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise IngestError(f"failed to fetch {url}: {exc}") from exc
    return _extract_html(resp.text, url, "url")
