"""Cross-references: one physical location, many catalog access points (§8.1). ZERO LLM calls.

`evals/misshelved.py` finds pages that fit a *different* book better than their own — 49% of the
live library. That is **not** a filing-error rate. *Inventory Turnover: Definition and Formula* is
filed under `KPI Dictionary` and fits `Inventory Management` better; **both are right**. It is a KPI
*definition* about *inventory*, and a single-parent tree (P4) forces an arbitrary choice.

Ranganathan's answer, and the library world's, is not to move the book. It is to **add an access
point**: the item stays where it is, and the other place where a reader would look for it gets a
cross-reference. `NodeMeta.see_also` is exactly that field, and it has been sitting unused.

Direction matters, and it is the reverse of what feels natural. Page P is filed in book A but its
content looks like book B. A reader asking about P's *content* gets routed toward **B** — and P is
not there. So the cross-reference goes **on B, pointing at P**. It rescues precisely the walk that
would otherwise fail.

This is a **materialized view over the catalog vectors** (P1): regenerated wholesale, never patched.
`origin="misroute"` scopes it, so hand-written `see_also` edges are never touched.

It is a HINT, not a gate (§7.4) — it only ever *adds* reachable pages to a menu. Nothing is hidden,
nothing is moved, and the citation still reports the page's true home.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from libkb.catalog.store import Catalog
from libkb.evals.misshelved import probe_misshelved
from libkb.library.models import ROOT_ID
from libkb.library.store import LibraryStore

log = structlog.get_logger(__name__)

ORIGIN = "misroute"


def _domain(shelf_path: str) -> str:
    """'Retail ▸ KPIs & Performance Analytics' → 'Retail'."""
    return shelf_path.split("▸")[0].strip()


@dataclass
class CrossLink:
    from_book: str  # the book that gets the cross-reference (the one a reader would search)
    to_page: str  # the page it points at (which lives somewhere else)
    to_path: str
    delta: float


@dataclass
class CrossLinkReport:
    considered: int = 0  # misshelved hits the probe found
    written: int = 0
    cleared: int = 0
    skipped_same_shelf: int = 0
    skipped_cross_domain: int = 0
    skipped_below_floor: int = 0
    skipped_over_cap: int = 0
    links: list[CrossLink] = field(default_factory=list)


def build_crosslinks(
    store: LibraryStore,
    catalog: Catalog,
    *,
    min_delta: float = 0.03,
    max_per_book: int = 3,
    dry_run: bool = False,
) -> CrossLinkReport:
    """Regenerate every machine-made cross-reference from the catalog vectors.

    Guard rails (the doc's own, §8.1 — plus one it did not foresee):
      - **cross-shelf only.** A pull to a sibling book on the same shelf is already solved: in shelf
        mode the whole shelf is laid out at once, so that page is on the menu regardless. Only a pull
        ACROSS shelves names a page the walk genuinely cannot see.
      - **within one domain.** Two reasons, and the second is the serious one. (1) A cross-domain
        pull is nearly always a false positive — on the live library both of them came from
        test-ingest artifacts, not from real facets. (2) **Privacy:** the Retail domain is private
        and gitignored (D-020) while the AI domain is tracked. A link written on an AI book carries
        the Retail page's title into a *tracked* `_meta.json` — a private-corpus leak straight into
        git. A derived artifact must not smuggle content across a trust boundary.
      - **`min_delta` floor**, or the report is noise: half the library "fits elsewhere" a little.
      - **`max_per_book` cap**, because max-pooling favours big books and an uncapped list would let
        one fat book paper the whole library with links (and re-inflate the menus §0a just shrank).
    """
    report = CrossLinkReport()
    probe = probe_misshelved(catalog)
    report.considered = len(probe.hits)

    keep: list = []
    for hit in probe.hits:
        if not hit.cross_shelf:
            report.skipped_same_shelf += 1
            continue
        if _domain(hit.own_shelf) != _domain(hit.best_shelf):
            report.skipped_cross_domain += 1
            continue
        if hit.delta < min_delta:
            report.skipped_below_floor += 1
            continue
        keep.append(hit)

    # hits arrive sorted by delta desc, so the cap keeps each book's STRONGEST pulls
    per_book: dict[str, int] = {}
    chosen: list = []
    for hit in keep:
        if per_book.get(hit.best_book_id, 0) >= max_per_book:
            report.skipped_over_cap += 1
            continue
        per_book[hit.best_book_id] = per_book.get(hit.best_book_id, 0) + 1
        chosen.append(hit)

    if dry_run:
        report.links = [
            CrossLink(hit.best_book, hit.page_title, store.path_str(hit.page_id), hit.delta)
            for hit in chosen
        ]
        return report

    # wholesale regeneration: clear ours everywhere first, so a link whose evidence disappeared
    # actually disappears. Manual edges (origin="manual") survive untouched.
    for meta in store.iter_subtree(ROOT_ID):
        if meta.kind != "page":
            report.cleared += store.clear_see_also(meta.id, origin=ORIGIN)

    for hit in chosen:
        note = f'"{hit.page_title}" is shelved elsewhere but belongs to this conversation'
        store.add_see_also(hit.best_book_id, hit.page_id, note, origin=ORIGIN)
        report.written += 1
        report.links.append(
            CrossLink(hit.best_book, hit.page_title, store.path_str(hit.page_id), hit.delta)
        )

    log.info(
        "crosslinks_built",
        considered=report.considered,
        written=report.written,
        cleared=report.cleared,
    )
    return report
