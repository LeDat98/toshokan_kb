"""Build eval cases from the card catalog.

Each catalog row is (question → the page it was generated from), so it is a labelled routing
example for free. We sample at most one question per page (so a content-rich page doesn't
dominate) with a fixed seed for reproducibility.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from libkb.catalog.store import Catalog
from libkb.library.models import slugify


@dataclass
class EvalCase:
    question: str
    lang: str
    target_page_id: str
    target_book_id: str
    target_path: str  # citation path of the target page (Domain ▸ … ▸ Page)


def build_cases(
    catalog: Catalog,
    *,
    limit: int = 20,
    domain: str | None = None,
    langs: tuple[str, ...] | None = None,
    seed: int = 13,
) -> list[EvalCase]:
    rows = catalog.all_questions()
    if domain:
        want = slugify(domain)
        rows = [r for r in rows if slugify(r["path"].split(" ▸ ")[0]) == want]
    if langs:
        rows = [r for r in rows if r["lang"] in langs]

    random.Random(seed).shuffle(rows)
    seen: set[str] = set()
    cases: list[EvalCase] = []
    for r in rows:
        if r["page_id"] in seen:
            continue  # at most one question per page
        seen.add(r["page_id"])
        cases.append(
            EvalCase(
                question=r["text"],
                lang=r["lang"],
                target_page_id=r["page_id"],
                target_book_id=r["book_id"],
                target_path=r["path"],
            )
        )
        if len(cases) >= limit:
            break
    return cases
