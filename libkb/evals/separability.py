"""Is a tree level worth committing to? Measure it — free, from vectors already in the catalog.

Two diagnostics, **zero LLM calls** (docs/ROUTING_REDESIGN.md §1):

1. **Sibling separability.** For every catalog question, build each book's centroid from its OWN
   question vectors with the query left out (leave-one-out), then ask whether the true book's
   centroid beats its shelf-siblings'. This measures whether the books are separable *by their own
   content* — descriptions are not involved. If two books cannot be told apart here, no amount of
   description-writing will make the `open_book` hop reliable: they are one book that got split.

2. **Route A vs Route B.** Same LOO machinery, two routes raced on the same questions:
     A: shelf → book → page   (the current walk: commit to a book, then pick a page inside it)
     B: shelf → page          (union TOC: rank every page on the shelf, no book commitment)
   Route A can lose a question forever — pick the wrong book and the right page is no longer in any
   menu the agent can see. Route B never makes that commitment. The rescue/loss counts say whether
   the book level is helping routing or hurting it.

Levels that are not separable should not be decision points. Measure BEFORE cutting a level.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np

from libkb.catalog.store import Catalog


@dataclass
class ShelfRow:
    shelf: str
    n_books: int
    n_questions: int
    accuracy: float
    n_pages: int = 0


@dataclass
class SeparabilityResult:
    n_decisions: int
    book_accuracy: float
    median_margin: float
    per_shelf: list[ShelfRow] = field(default_factory=list)
    confusions: list[tuple[str, str, int]] = field(default_factory=list)


@dataclass
class RouteComparison:
    n: int
    route_a_acc: float  # shelf → book → page, end to end
    book_hop_acc: float  # just the book hop
    route_b_acc: float  # shelf → page, book level deleted
    rescues: int  # B right where A was wrong
    losses: int  # A right where B is wrong
    median_book_margin: float
    median_page_margin: float

    @property
    def delta(self) -> float:
        return self.route_b_acc - self.route_a_acc


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n else v


def probe_separability(catalog: Catalog) -> tuple[SeparabilityResult, RouteComparison]:
    matrix, rows = catalog.vectors()
    n = len(rows)
    if n < 4:
        return SeparabilityResult(0, 0.0, 0.0), RouteComparison(0, 0, 0, 0, 0, 0, 0, 0)

    # path = "Domain ▸ Shelf ▸ Book ▸ Page" → everything above the book is the shelf key
    shelf_of: list[str] = []
    book_title: dict[str, str] = {}
    for r in rows:
        parts = [p.strip() for p in r["path"].split("▸")]
        shelf_of.append(" ▸ ".join(parts[:-2]) if len(parts) >= 3 else "(root)")
        book_title[r["book_id"]] = parts[-2] if len(parts) >= 2 else r["book_id"]

    page_of = [r["page_id"] for r in rows]
    book_of = [r["book_id"] for r in rows]

    book_rows: dict[str, list[int]] = defaultdict(list)
    page_rows: dict[str, list[int]] = defaultdict(list)
    shelf_books: dict[str, set[str]] = defaultdict(set)
    shelf_pages: dict[str, set[str]] = defaultdict(set)
    for i in range(n):
        book_rows[book_of[i]].append(i)
        page_rows[page_of[i]].append(i)
        shelf_books[shelf_of[i]].add(book_of[i])
        shelf_pages[shelf_of[i]].add(page_of[i])

    book_sum = {b: matrix[idx].sum(axis=0) for b, idx in book_rows.items()}
    page_sum = {p: matrix[idx].sum(axis=0) for p, idx in page_rows.items()}

    def centroid(total: np.ndarray, count: int, drop: np.ndarray | None) -> np.ndarray | None:
        """Leave-one-out centroid: remove the query's own vector from its own group."""
        if drop is not None:
            count -= 1
            if count <= 0:
                return None
            total = total - drop
        return _unit(total / count) if count > 0 else None

    book_ok = np.zeros(n, dtype=bool)
    book_margins: list[float] = []
    a_ok = np.zeros(n, dtype=bool)
    b_ok = np.zeros(n, dtype=bool)
    page_margins: list[float] = []
    evaluated = np.zeros(n, dtype=bool)
    confusion: Counter[tuple[str, str]] = Counter()
    per_shelf_hits: dict[str, list[int]] = defaultdict(list)

    for i in range(n):
        shelf = shelf_of[i]
        siblings = shelf_books[shelf]
        if len(siblings) < 2:
            continue  # no book decision to make on a one-book shelf
        v = matrix[i]

        # --- the book hop: does the true book's own content beat its siblings? ---
        scored: list[tuple[float, str]] = []
        for b in siblings:
            drop = v if b == book_of[i] else None
            c = centroid(book_sum[b], len(book_rows[b]), drop)
            if c is not None:
                scored.append((float(v @ c), b))
        if len(scored) < 2:
            continue
        scored.sort(reverse=True)
        evaluated[i] = True
        winner_book = scored[0][1]
        book_margins.append(scored[0][0] - scored[1][0])
        book_ok[i] = winner_book == book_of[i]
        per_shelf_hits[shelf].append(1 if book_ok[i] else 0)
        if not book_ok[i]:
            confusion[(book_title[book_of[i]], book_title[winner_book])] += 1

        # --- route A: commit to the chosen book, then pick a page INSIDE it ---
        def best_page(pages: set[str], vec: np.ndarray = v, idx: int = i) -> tuple[str, float]:
            ranked: list[tuple[float, str]] = []
            for p in pages:
                drop = vec if p == page_of[idx] else None
                c = centroid(page_sum[p], len(page_rows[p]), drop)
                if c is not None:
                    ranked.append((float(vec @ c), p))
            if not ranked:
                return "", 0.0
            ranked.sort(reverse=True)
            gap = ranked[0][0] - ranked[1][0] if len(ranked) > 1 else ranked[0][0]
            return ranked[0][1], gap

        pages_in_winner = {
            p for p in shelf_pages[shelf] if _book_of_page(p, page_rows, book_of) == winner_book
        }
        pick_a, _ = best_page(pages_in_winner)
        a_ok[i] = pick_a == page_of[i]

        # --- route B: no book commitment — rank every page on the shelf ---
        pick_b, gap_b = best_page(shelf_pages[shelf])
        b_ok[i] = pick_b == page_of[i]
        page_margins.append(gap_b)

    m = evaluated
    total = int(m.sum())
    if total == 0:
        return SeparabilityResult(0, 0.0, 0.0), RouteComparison(0, 0, 0, 0, 0, 0, 0, 0)

    per_shelf = [
        ShelfRow(
            shelf=s,
            n_books=len(shelf_books[s]),
            n_questions=len(hits),
            accuracy=sum(hits) / len(hits),
            n_pages=len(shelf_pages[s]),
        )
        for s, hits in per_shelf_hits.items()
    ]
    per_shelf.sort(key=lambda r: r.accuracy)

    sep = SeparabilityResult(
        n_decisions=total,
        book_accuracy=float(book_ok[m].mean()),
        median_margin=float(np.median(book_margins)) if book_margins else 0.0,
        per_shelf=per_shelf,
        confusions=[(a, b, c) for (a, b), c in confusion.most_common(8)],
    )
    routes = RouteComparison(
        n=total,
        route_a_acc=float(a_ok[m].mean()),
        book_hop_acc=float(book_ok[m].mean()),
        route_b_acc=float(b_ok[m].mean()),
        rescues=int((b_ok & ~a_ok & m).sum()),
        losses=int((a_ok & ~b_ok & m).sum()),
        median_book_margin=float(np.median(book_margins)) if book_margins else 0.0,
        median_page_margin=float(np.median(page_margins)) if page_margins else 0.0,
    )
    return sep, routes


def _book_of_page(page_id: str, page_rows: dict[str, list[int]], book_of: list[str]) -> str:
    return book_of[page_rows[page_id][0]]
