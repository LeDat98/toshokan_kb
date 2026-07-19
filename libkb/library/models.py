from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from ulid import ULID

NodeKind = Literal["root", "domain", "shelf", "book", "page"]
NodeID = str

ROOT_ID: NodeID = "nd_root"
UNCATALOGUED_ID: NodeID = "nd_uncatalogued"

# storage is a strict tree (principle P4); which child kinds each kind may hold
VALID_CHILD: dict[str, set[str]] = {
    "root": {"domain"},
    "domain": {"shelf"},
    "shelf": {"shelf", "book"},
    "book": {"page"},
    "page": set(),
}

# subdirectory a child kind lives in, under its parent's directory
KIND_DIR = {"domain": "domains", "shelf": "shelves", "book": "books"}


def new_node_id() -> NodeID:
    # ULIDs: immutable, sortable, never reused (principle P5)
    return f"nd_{ULID()}"


MAX_SLUG = 60


def slugify(text: str) -> str:
    """A slug is a filename, and a filename has a hard limit that a title does not.

    A news headline can run to 200 characters; nest that inside
    `library/domains/…/shelves/…/books/…/pages/` and Windows refuses the write at 260 (a real crash
    on the MultiHop corpus, not a hypothetical). Truncation is safe here because `write_page`
    already prefixes an ordinal (`007-…`) that is unique within the book, and because the TITLE —
    the thing anyone reads or cites — is stored in full inside the file, never in its name.
    """
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text[:MAX_SLUG].rstrip("-") or "untitled")


def one_line_of(text: str, limit: int = 160) -> str:
    stripped = text.strip()
    line = stripped.splitlines()[0].strip() if stripped else ""
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


class NodeRef(BaseModel):
    id: NodeID
    kind: NodeKind
    title: str
    slug: str


class SeeAlso(BaseModel):
    target: NodeRef
    note: str
    origin: Literal["manual", "misroute"] = "manual"


class NodeStats(BaseModel):
    n_shelves: int = 0
    n_books: int = 0
    n_pages: int = 0
    last_ingest_at: datetime | None = None


class NodeMeta(BaseModel):
    id: NodeID
    kind: NodeKind
    slug: str
    title: str
    description: str = ""  # materialized view — write only via library/views.py (principle P1)
    description_rev: int = 0
    parent_id: NodeID | None = None
    see_also: list[SeeAlso] = Field(default_factory=list)
    stats: NodeStats = Field(default_factory=NodeStats)
    uncatalogued: bool = False
    created_at: datetime
    updated_at: datetime


class NodeCard(BaseModel):
    """Compact projection the navigator reads in a menu — keep small."""

    id: NodeID
    kind: NodeKind
    title: str
    one_line: str = ""
    stats_line: str = ""
    see_also: list[str] = Field(default_factory=list)


class TOCEntry(BaseModel):
    page_id: NodeID
    title: str
    one_line: str = ""
    keywords: list[str] = Field(default_factory=list)


class Chapter(BaseModel):
    title: str
    entries: list[TOCEntry] = Field(default_factory=list)


class TOC(BaseModel):
    book_id: NodeID
    chapters: list[Chapter] = Field(default_factory=list)


class PageContent(BaseModel):
    page_id: NodeID
    book_id: NodeID
    title: str
    markdown: str
    source_ref: str | None = None
    # False for back matter (a bibliography, an acknowledgements page). It stays in the book and can
    # be read; it is simply never given to the card catalog, so the sieve cannot offer it as
    # evidence. Absent from a page file ⇒ True.
    indexable: bool = True


class Redirect(BaseModel):
    old_id: NodeID
    new_id: NodeID
    reason: Literal["move", "split", "merge"]
    at: datetime
