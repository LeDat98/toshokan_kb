"""Shelf-reading: which pages fit a different book better than their own? (§8.1) — ZERO LLM calls.

A librarian walks the stacks asking of each spine: *does this belong here?* The machine version: for
each page, rank every book by MAX-similarity over that book's **other** pages (the page's own rows
are excluded — leave-one-out), then report the pages whose best-fitting book is not the one they are
filed in.

**Read the output correctly — it is NOT a list of filing errors.** *Inventory Turnover: Definition
and Formula* is filed under `KPI Dictionary` and fits `Inventory Management` better. Which is right?
**Both.** It is a KPI *definition* about *inventory* — a two-faceted item, and a single-parent tree
forces an arbitrary choice. The library world's answer is not to move the book. It is **one physical
location, many catalog access points**: a cross-reference. So this probe feeds
`library/crosslinks.py`, which writes `see_also` edges — it is NOT a move queue.

Only a *bidirectional* theft (two books stealing from each other, §1.2) means one book was split in
two, and that is a merge candidate for a human.

**Pooling is mean where the thing is one topic, max where it is a union** (§7.2) — and the two
sides of this comparison are different kinds of thing:

- a **page** is one topic ⇒ represent it by the **centroid** of its question vectors;
- a **book** is a union of topics ⇒ score it by the **max** over its individual question vectors.
  Its centroid would sit in empty space, resembling nothing it holds.

Using max on both sides instead inflates the hit rate (58% vs 49%) and the deltas, because a page
with 8 questions gets 8 chances to spike against any book. Reproduces the doc's numbers exactly:
**56 of 115 pages (49%), top delta +0.078.**

Known bias (the doc's own guard rail (b)): a max still favours books with more rows, since more rows
means more chances at a high max. `size_bias` measures how strong that is instead of assuming.

Known blind spot: a **single-page book cannot be judged at all**. Leave-one-out removes the page's
own rows, and a one-page book has nothing left to compare against — its own score is undefined. Such
pages are skipped rather than reported with a fabricated delta, so they are invisible here.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np

from libkb.catalog.store import Catalog


@dataclass
class Misshelved:
    page_id: str
    page_title: str
    own_book_id: str
    own_book: str
    own_shelf: str
    best_book_id: str
    best_book: str
    best_shelf: str
    delta: float  # how much better the other book fits — the strength of the pull
    own_score: float
    best_score: float

    @property
    def cross_shelf(self) -> bool:
        return self.own_shelf != self.best_shelf


@dataclass
class MisshelvedReport:
    n_pages: int
    hits: list[Misshelved] = field(default_factory=list)  # sorted by delta desc
    mutual: list[tuple[str, str, int, int]] = field(default_factory=list)  # a, b, a→b, b→a
    size_bias: float = 0.0  # mean rows of "thief" books ÷ mean rows of all books; 1.0 = no bias

    @property
    def rate(self) -> float:
        return len(self.hits) / self.n_pages if self.n_pages else 0.0


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n else v


def probe_misshelved(catalog: Catalog, *, min_delta: float = 0.0) -> MisshelvedReport:
    matrix, rows = catalog.vectors()
    if len(rows) < 4:
        return MisshelvedReport(0)

    page_rows: dict[str, list[int]] = defaultdict(list)
    book_rows: dict[str, list[int]] = defaultdict(list)
    book_of_page: dict[str, str] = {}
    title: dict[str, str] = {}  # page_id / book_id → display title
    shelf_of_book: dict[str, str] = {}

    for i, r in enumerate(rows):
        parts = [p.strip() for p in r["path"].split("▸")]
        page_rows[r["page_id"]].append(i)
        book_rows[r["book_id"]].append(i)
        book_of_page[r["page_id"]] = r["book_id"]
        title[r["page_id"]] = parts[-1] if parts else r["page_id"]
        title[r["book_id"]] = parts[-2] if len(parts) >= 2 else r["book_id"]
        shelf_of_book[r["book_id"]] = " ▸ ".join(parts[:-2]) if len(parts) >= 3 else "(root)"

    books = list(book_rows)
    hits: list[Misshelved] = []
    theft: Counter[tuple[str, str]] = Counter()

    for page_id, own_rows in page_rows.items():
        own_book = book_of_page[page_id]
        centroid = _unit(matrix[own_rows].mean(axis=0))  # a page is ONE topic → mean
        own_set = set(own_rows)

        scored: list[tuple[float, str]] = []
        for b in books:
            # leave-one-out: a book may never match a page using that page's own rows
            other = [i for i in book_rows[b] if i not in own_set]
            if not other:
                continue
            scored.append((float((matrix[other] @ centroid).max()), b))  # a book is a UNION → max
        if len(scored) < 2:
            continue
        scored.sort(reverse=True)

        best_score, best_book = scored[0]
        own_score = next((s for s, b in scored if b == own_book), 0.0)
        if best_book == own_book:
            continue
        delta = best_score - own_score
        if delta < min_delta:
            continue
        theft[(title[own_book], title[best_book])] += 1
        hits.append(
            Misshelved(
                page_id=page_id,
                page_title=title[page_id],
                own_book_id=own_book,
                own_book=title[own_book],
                own_shelf=shelf_of_book[own_book],
                best_book_id=best_book,
                best_book=title[best_book],
                best_shelf=shelf_of_book[best_book],
                delta=delta,
                own_score=own_score,
                best_score=best_score,
            )
        )

    hits.sort(key=lambda h: h.delta, reverse=True)

    # bidirectional theft = one book that got split in two (§1.2). Everything else is a facet.
    mutual: list[tuple[str, str, int, int]] = []
    for (a, b), n_ab in theft.items():
        n_ba = theft.get((b, a), 0)
        if n_ba and a < b:  # emit each pair once
            mutual.append((a, b, n_ab, n_ba))
    mutual.sort(key=lambda t: -(t[2] + t[3]))

    return MisshelvedReport(
        n_pages=len(page_rows),
        hits=hits,
        mutual=mutual,
        size_bias=_size_bias(hits, book_rows),
    )


def _size_bias(hits: list[Misshelved], book_rows: dict[str, list[int]]) -> float:
    """Do the books that 'steal' pages simply have more rows to win a max with? 1.0 = no bias."""
    if not hits or not book_rows:
        return 0.0
    mean_all = float(np.mean([len(v) for v in book_rows.values()]))
    mean_thief = float(np.mean([len(book_rows[h.best_book_id]) for h in hits]))
    return mean_thief / mean_all if mean_all else 0.0
