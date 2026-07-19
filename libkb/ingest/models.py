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
    # Back matter (References, Bibliography, Acknowledgements) is part of the document but is not
    # knowledge: it answers no question a reader asks of the library. It stays on the shelf and can
    # still be read; it just never enters the card catalog, so the sieve cannot propose it as
    # evidence. Before this, our LARGEST page was a bibliography — indexed and retrievable.
    indexable: bool = True


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
    # A page written to the library but missing from the catalog is INVISIBLE to the sieve — it may
    # as well not have been imported. That used to be a log line; now it is a number the CLI prints
    # in red, because an import that silently loses 21% of the corpus looks exactly like one that
    # worked (D-040).
    indexed_pages: int = 0
    index_failures: list[str] = field(default_factory=list)
    shelf_strategy: str = ""
    provided: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)  # book paths created
