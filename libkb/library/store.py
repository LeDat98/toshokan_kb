"""Filesystem-backed tree store for the library.

Layout (see docs/ARCHITECTURE.md §3):
    library/_meta.json                          root node
    library/domains/<slug>/_meta.json           domain
    .../shelves/<slug>/_meta.json               shelf (nestable)
    .../books/<slug>/{_meta.json, toc.json, pages/NNN-<slug>.md}
    library/_uncatalogued/                      review shelf (principle P10)

Invariants:
- Node IDs are ULIDs, immutable, never reused (P5). `move()` keeps the ID, so no
  redirect is needed; ID-changing redirects arrive with split/merge in P4.
- `set_description` is only called by library/views.py (P1) — enforced by test.
- All writes are atomic (temp file + os.replace).
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import structlog
from pydantic import BaseModel

from libkb.exceptions import InvalidParent, NodeNotFound, SlugCollision
from libkb.library.models import (
    KIND_DIR,
    ROOT_ID,
    TOC,
    UNCATALOGUED_ID,
    VALID_CHILD,
    Chapter,
    NodeCard,
    NodeID,
    NodeKind,
    NodeMeta,
    NodeRef,
    NodeStats,
    PageContent,
    SeeAlso,
    TOCEntry,
    new_node_id,
    one_line_of,
    slugify,
)

log = structlog.get_logger(__name__)


@dataclass
class _Entry:
    path: Path  # directory for containers, .md file for pages
    kind: NodeKind
    parent_id: NodeID | None


class LibraryStore:
    def __init__(self, root_dir: Path | str) -> None:
        self.root_dir = Path(root_dir)
        self._index: dict[NodeID, _Entry] = {}
        if (self.root_dir / "_meta.json").exists():
            self._scan()

    # ------------------------------------------------------------- bootstrap

    def init_library(self) -> None:
        if (self.root_dir / "_meta.json").exists():
            self._scan()
            return
        (self.root_dir / "domains").mkdir(parents=True, exist_ok=True)
        (self.root_dir / "_catalog").mkdir(exist_ok=True)
        now = _now()
        root = NodeMeta(
            id=ROOT_ID,
            kind="root",
            slug="library",
            title="Library",
            description="Root of the knowledge library.",
            created_at=now,
            updated_at=now,
        )
        _write_json(self.root_dir / "_meta.json", root)
        uncat_dir = self.root_dir / "_uncatalogued"
        (uncat_dir / "books").mkdir(parents=True, exist_ok=True)
        uncat = NodeMeta(
            id=UNCATALOGUED_ID,
            kind="shelf",
            slug="uncatalogued",
            title="Uncatalogued",
            description=(
                "New arrivals whose classification confidence was below the gate. "
                "They wait here for review — nothing gets force-filed."
            ),
            parent_id=ROOT_ID,
            uncatalogued=True,
            created_at=now,
            updated_at=now,
        )
        _write_json(uncat_dir / "_meta.json", uncat)
        self._scan()
        log.info("library_initialized", path=str(self.root_dir))

    # ------------------------------------------------------------------ read

    def get(self, node_id: NodeID) -> NodeMeta:
        entry = self._entry(node_id)
        if entry.kind == "page":
            front, _ = _read_page_file(entry.path)
            ts = datetime.fromtimestamp(entry.path.stat().st_mtime, tz=UTC)
            return NodeMeta(
                id=node_id,
                kind="page",
                slug=entry.path.stem,
                title=front.get("title", entry.path.stem),
                parent_id=entry.parent_id,
                created_at=ts,
                updated_at=ts,
            )
        return _read_meta(entry.path / "_meta.json")

    def children(self, node_id: NodeID) -> list[NodeCard]:
        """THE MENU — what the navigator reads at each hop."""
        entry = self._entry(node_id)
        if entry.kind == "page":
            raise InvalidParent("pages have no children")
        if entry.kind == "book":
            return [
                NodeCard(
                    id=e.page_id, kind="page", title=e.title, one_line=e.one_line,
                    stats_line=f"keywords: {', '.join(e.keywords)}" if e.keywords else "",
                )
                for chapter in self.toc(node_id).chapters
                for e in chapter.entries
            ]
        cards = [
            self._card(_read_meta(child.path / "_meta.json"))
            for child in self._index.values()
            if child.parent_id == node_id and child.kind != "page"
        ]
        cards.sort(key=lambda c: c.title.lower())
        return cards

    def toc(self, book_id: NodeID) -> TOC:
        entry = self._entry(book_id)
        if entry.kind != "book":
            raise NodeNotFound(f"{book_id} is not a book")
        path = entry.path / "toc.json"
        if not path.exists():
            return TOC(book_id=book_id)
        return TOC.model_validate_json(path.read_text(encoding="utf-8"))

    def page(self, page_id: NodeID) -> PageContent:
        entry = self._entry(page_id)
        if entry.kind != "page":
            raise NodeNotFound(f"{page_id} is not a page")
        front, body = _read_page_file(entry.path)
        return PageContent(
            page_id=page_id,
            book_id=entry.parent_id or "",
            title=front.get("title", entry.path.stem),
            markdown=body,
            source_ref=front.get("source_ref") or None,
        )

    def path_of(self, node_id: NodeID) -> list[NodeRef]:
        refs: list[NodeRef] = []
        current: NodeID | None = node_id
        while current is not None:
            entry = self._entry(current)
            meta = self.get(current)
            refs.append(NodeRef(id=meta.id, kind=meta.kind, title=meta.title, slug=meta.slug))
            current = entry.parent_id
        refs.reverse()
        return refs

    def path_str(self, node_id: NodeID, *, sep: str = " ▸ ") -> str:
        """Citation string (principle P6), root omitted: 'AI ▸ RAG ▸ Book ▸ Page'."""
        return sep.join(r.title for r in self.path_of(node_id) if r.kind != "root")

    def iter_subtree(self, node_id: NodeID = ROOT_ID) -> Iterator[NodeMeta]:
        meta = self.get(node_id)
        yield meta
        if meta.kind == "page":
            return
        for child_id, entry in list(self._index.items()):
            if entry.parent_id == node_id:
                yield from self.iter_subtree(child_id)

    def resolve_path(self, human_path: str) -> NodeID:
        """'ai/rag/advanced-rag-techniques' → node id (containers only)."""
        current = ROOT_ID
        for part in [p for p in human_path.strip("/").split("/") if p]:
            match = next(
                (
                    child_id
                    for child_id, entry in self._index.items()
                    if entry.parent_id == current
                    and entry.kind != "page"
                    and entry.path.name.lstrip("_") == part
                ),
                None,
            )
            if match is None:
                raise NodeNotFound(f"no node '{part}' in path '{human_path}'")
            current = match
        return current

    # ----------------------------------------------------------------- write

    def create(
        self, parent_id: NodeID, kind: NodeKind, title: str, description: str = ""
    ) -> NodeMeta:
        parent = self._entry(parent_id)
        if kind == "page" or kind not in VALID_CHILD.get(parent.kind, set()):
            raise InvalidParent(
                f"cannot create '{kind}' under '{parent.kind}' "
                f"(pages go through write_page)"
            )
        slug = slugify(title)
        target = parent.path / KIND_DIR[kind] / slug
        if target.exists():
            raise SlugCollision(f"'{slug}' already exists under {parent.path.name}")
        target.mkdir(parents=True)
        now = _now()
        meta = NodeMeta(
            id=new_node_id(),
            kind=kind,
            slug=slug,
            title=title,
            description=description,
            description_rev=1 if description else 0,
            parent_id=parent_id,
            created_at=now,
            updated_at=now,
        )
        _write_json(target / "_meta.json", meta)
        if kind == "book":
            (target / "pages").mkdir()
            _write_json(target / "toc.json", TOC(book_id=meta.id))
        self._index[meta.id] = _Entry(target, kind, parent_id)
        return meta

    def write_page(
        self,
        book_id: NodeID,
        title: str,
        markdown: str,
        *,
        chapter: str = "Contents",
        one_line: str = "",
        keywords: list[str] | None = None,
        source_ref: str | None = None,
    ) -> NodeMeta:
        entry = self._entry(book_id)
        if entry.kind != "book":
            raise InvalidParent(f"{book_id} is not a book")
        toc = self.toc(book_id)
        number = sum(len(c.entries) for c in toc.chapters) + 1
        path = entry.path / "pages" / f"{number:03d}-{slugify(title)}.md"
        if path.exists():
            raise SlugCollision(f"page file {path.name} already exists")
        page_id = new_node_id()
        _write_page_file(
            path, {"id": page_id, "title": title, "source_ref": source_ref or ""}, markdown
        )
        target_chapter = next((c for c in toc.chapters if c.title == chapter), None)
        if target_chapter is None:
            target_chapter = Chapter(title=chapter)
            toc.chapters.append(target_chapter)
        target_chapter.entries.append(
            TOCEntry(page_id=page_id, title=title, one_line=one_line, keywords=keywords or [])
        )
        self.write_toc(book_id, toc)
        self._index[page_id] = _Entry(path, "page", book_id)
        now = _now()
        return NodeMeta(
            id=page_id, kind="page", slug=path.stem, title=title, parent_id=book_id,
            created_at=now, updated_at=now,
        )

    def write_toc(self, book_id: NodeID, toc: TOC) -> None:
        entry = self._entry(book_id)
        if entry.kind != "book":
            raise InvalidParent(f"{book_id} is not a book")
        _write_json(entry.path / "toc.json", toc)

    def set_description(self, node_id: NodeID, text: str, rev: int) -> None:
        """Only library/views.py may call this (principle P1) — see tests/test_conventions.py."""
        entry = self._entry(node_id)
        if entry.kind == "page":
            raise InvalidParent("pages have no description; edit TOC one_line instead")
        meta = self.get(node_id)
        meta.description = text
        meta.description_rev = rev
        meta.updated_at = _now()
        _write_json(entry.path / "_meta.json", meta)

    def add_see_also(
        self, node_id: NodeID, target_id: NodeID, note: str, origin: str = "manual"
    ) -> None:
        entry = self._entry(node_id)
        if entry.kind == "page":
            raise InvalidParent("see-also lives on containers, not pages")
        meta = self.get(node_id)
        if any(sa.target.id == target_id for sa in meta.see_also):
            return
        target = self.get(target_id)
        meta.see_also.append(
            SeeAlso(
                target=NodeRef(id=target.id, kind=target.kind, title=target.title, slug=target.slug),
                note=note,
                origin=origin,  # type: ignore[arg-type]
            )
        )
        meta.updated_at = _now()
        _write_json(entry.path / "_meta.json", meta)

    def move(self, node_id: NodeID, new_parent_id: NodeID) -> None:
        """Relocate a subtree. The node keeps its ID, so existing references stay valid."""
        entry = self._entry(node_id)
        if entry.kind in ("root", "page"):
            raise InvalidParent("cannot move root or individual pages")
        new_parent = self._entry(new_parent_id)
        if entry.kind not in VALID_CHILD.get(new_parent.kind, set()):
            raise InvalidParent(f"'{entry.kind}' cannot live under '{new_parent.kind}'")
        target_dir = new_parent.path / KIND_DIR[entry.kind]
        target_dir.mkdir(exist_ok=True)
        target = target_dir / entry.path.name
        if target.exists():
            raise SlugCollision(f"'{entry.path.name}' already exists at destination")
        shutil.move(str(entry.path), str(target))
        meta = _read_meta(target / "_meta.json")
        meta.parent_id = new_parent_id
        meta.updated_at = _now()
        _write_json(target / "_meta.json", meta)
        self._scan()
        log.info("node_moved", node=node_id, to=new_parent_id)

    def recompute_stats(self, node_id: NodeID = ROOT_ID) -> NodeStats:
        entry = self._entry(node_id)
        if entry.kind == "page":
            return NodeStats()
        stats = NodeStats()
        for child_id, child in list(self._index.items()):
            if child.parent_id != node_id:
                continue
            if child.kind == "page":
                stats.n_pages += 1
                continue
            child_stats = self.recompute_stats(child_id)
            stats.n_shelves += child_stats.n_shelves + (1 if child.kind == "shelf" else 0)
            stats.n_books += child_stats.n_books + (1 if child.kind == "book" else 0)
            stats.n_pages += child_stats.n_pages
        meta = self.get(node_id)
        meta.stats = stats
        meta.updated_at = _now()
        _write_json(entry.path / "_meta.json", meta)
        return stats

    # -------------------------------------------------------------- internal

    def _entry(self, node_id: NodeID) -> _Entry:
        entry = self._index.get(node_id)
        if entry is None:
            raise NodeNotFound(node_id)
        return entry

    def _card(self, meta: NodeMeta) -> NodeCard:
        s = meta.stats
        if meta.kind == "domain":
            stats_line = f"{s.n_shelves} shelves · {s.n_books} books"
        elif meta.kind == "shelf":
            stats_line = f"{s.n_books} books" + (
                f" · {s.n_shelves} sub-shelves" if s.n_shelves else ""
            )
        elif meta.kind == "book":
            stats_line = f"{s.n_pages} pages"
        else:
            stats_line = ""
        return NodeCard(
            id=meta.id,
            kind=meta.kind,
            title=meta.title,
            one_line=one_line_of(meta.description),
            stats_line=stats_line,
            see_also=[f"{sa.note} — see: {sa.target.title}" for sa in meta.see_also],
        )

    def _scan(self) -> None:
        self._index.clear()
        root_meta = _read_meta(self.root_dir / "_meta.json")
        self._index[root_meta.id] = _Entry(self.root_dir, "root", None)
        self._scan_container(self.root_dir, root_meta.id)
        uncat_dir = self.root_dir / "_uncatalogued"
        if (uncat_dir / "_meta.json").exists():
            uncat_meta = _read_meta(uncat_dir / "_meta.json")
            self._index[uncat_meta.id] = _Entry(uncat_dir, uncat_meta.kind, ROOT_ID)
            self._scan_container(uncat_dir, uncat_meta.id)

    def _scan_container(self, directory: Path, node_id: NodeID) -> None:
        for sub in ("domains", "shelves", "books"):
            parent = directory / sub
            if not parent.is_dir():
                continue
            for child in sorted(parent.iterdir()):
                meta_file = child / "_meta.json"
                if not meta_file.exists():
                    continue
                meta = _read_meta(meta_file)
                self._index[meta.id] = _Entry(child, meta.kind, node_id)
                self._scan_container(child, meta.id)
        pages = directory / "pages"
        if pages.is_dir():
            for page_file in sorted(pages.glob("*.md")):
                front, _ = _read_page_file(page_file)
                page_id = front.get("id")
                if page_id:
                    self._index[page_id] = _Entry(page_file, "page", node_id)


# ------------------------------------------------------------------- helpers


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _write_json(path: Path, model: BaseModel) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_meta(path: Path) -> NodeMeta:
    if not path.exists():
        raise NodeNotFound(str(path))
    return NodeMeta.model_validate_json(path.read_text(encoding="utf-8"))


def _write_page_file(path: Path, front: dict[str, str], body: str) -> None:
    lines = ["---"]
    lines += [f"{key}: {value}" for key, value in front.items() if value]
    lines += ["---", "", body.strip(), ""]
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, path)


def _read_page_file(path: Path) -> tuple[dict[str, str], str]:
    if not path.exists():
        raise NodeNotFound(str(path))
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return {}, text
    front: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" in line:
            key, value = line.split(":", 1)
            front[key.strip()] = value.strip()
    return front, "\n".join(lines[end + 1 :]).strip()
