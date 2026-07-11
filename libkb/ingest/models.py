"""The DraftTree — the intermediate contract between ingest stages (see docs/INGEST.md).

A source SURVEY fills the slots it can and marks the rest missing; RESOLVE fills the gaps;
IMPORTER commits into the LibraryStore.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# the five structural levels
LEVELS = ("domain", "shelf", "book", "page", "description")


@dataclass
class DraftPage:
    title: str
    body_markdown: str
    one_line: str = ""
    keywords: list[str] = field(default_factory=list)
    source_ref: str = ""


@dataclass
class DraftBook:
    title: str
    pages: list[DraftPage] = field(default_factory=list)
    description: str = ""
    source_ref: str = ""
    priority: str | None = None  # "P0" | "P1" | "P2" if the source encoded one


@dataclass
class DraftShelf:
    title: str
    description: str = ""
    books: list[DraftBook] = field(default_factory=list)


@dataclass
class DraftTree:
    domain_title: str
    domain_description: str = ""
    books: list[DraftBook] = field(default_factory=list)  # flat, before shelf resolution
    shelves: list[DraftShelf] = field(default_factory=list)  # after resolution
    provided: set[str] = field(default_factory=set)  # levels the source gave
    missing: set[str] = field(default_factory=set)  # levels to fill

    @property
    def n_pages(self) -> int:
        return sum(len(b.pages) for b in self.books)


@dataclass
class ImportReport:
    domain: str
    shelves: int = 0
    books: int = 0
    pages: int = 0
    skipped_pages: int = 0
    shelf_strategy: str = ""
    provided: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)  # book paths created
