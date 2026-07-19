"""MultiHop-RAG: 2,556 ground-truth queries, and the first honest verdict on WHAT to index (D-039).

Two things this corpus settles that ours could not, because ours is 231 pages and 30 questions:

**1. Question-index vs text-index, at n=2,255 instead of n=30.** `probe-index` on our own library
gave two regimes that flatly contradicted each other, and the reason was a rigged test: in the LOI
regime the query is a question the LLM GENERATED FROM THE PAGE, so embedding the page body and
matching that question back is near-tautological — text won by 24 points on a paper it had already
seen. Here the queries are external. Nothing generated them from our pages.

**2. Multi-hop evidence — the synthesis question we have been dodging.** Each answerable query cites
2–3 DIFFERENT articles, so "did a gold article make top-k" is the wrong question. Three metrics, in
increasing order of what an answer actually needs:

    Hit@k       ≥1 gold article in the top k          — the loosest thing anyone reports
    Coverage@k  the FRACTION of gold articles found   — how much of the evidence we assembled
    AllGold@k   EVERY gold article in the top k       — what a correct multi-hop answer requires

The cascade opens a basket of 3 (`cascade_max_pages`), so AllGold@3 is the evidence the answerer ever
actually sees.

⚠️ **It is NOT the ceiling on the answer, and I claimed it was (D-042).** MEASURED: `inference`
queries score AllGold@3 = 14.0% and still get **93.8%** of their answers right. `evidence_list` names
*every* fact that supports an answer, not the *minimum set needed* to reach it — "who in crypto is on
trial for fraud?" needs one article naming Sam Bankman-Fried, not all three. So read AllGold as a
strict measure of **evidence assembly**, which is what it is, and never as a bound on accuracy, which
is what I turned it into before a run refuted me.

Where multiple documents genuinely ARE required — `comparison` and `temporal` — the answer scores do
track it (60.6% and 65.2%), and that is the gap a bigger basket has to close.

The 301 `null_query` rows have **zero evidence** and the answer "Insufficient information." They are
unscoreable for retrieval and are excluded here — but they are the point of the *cascade* eval,
where they test the rule this project calls non-negotiable: no evidence ⇒ honest NOT_FOUND (P6).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import structlog

from libkb.catalog.store import Catalog
from libkb.evals.indexing import _Index, fuse
from libkb.ingest.frontmatter import split_frontmatter
from libkb.library.sections import split_sections
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)

INDEXES = ("questions", "text", "sections", "both")
_MAX_CHARS = 8000
# k=3 is the cascade's basket (`cascade_max_pages`) and k=20 is what it fetches (`cascade_fetch_n`).
# Those two are not arbitrary reporting points: they are the live system's actual operating points,
# so a column here is a claim about the live system and not about a benchmark.
KS = (1, 3, 5, 10, 20)


@dataclass
class Query:
    text: str
    kind: str
    gold: set[str]  # article titles the evidence comes from


@dataclass
class MultihopRow:
    index: str
    kind: str  # all | inference_query | comparison_query | temporal_query
    n: int
    hit: dict[int, float] = field(default_factory=dict)
    coverage: dict[int, float] = field(default_factory=dict)
    allgold: dict[int, float] = field(default_factory=dict)


def load_queries(path: Path | str) -> list[Query]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    out: list[Query] = []
    for row in rows:
        gold = {e["title"] for e in row.get("evidence_list", [])}
        if gold:  # null_query has none — it belongs to the cascade eval, not to retrieval
            out.append(Query(row["query"], row["question_type"], gold))
    return out


def article_of_page(store: LibraryStore, src_root: Path) -> dict[str, str]:
    """page_id → the ARTICLE it came from.

    A page knows its `source_ref` (the .md it was split out of); the .md knows its article title in
    frontmatter. Going through the file rather than the page title matters: the splitter renames a
    cut page `Title — 2 Section`, so page titles are not article titles.
    """
    title_of_file: dict[str, str] = {}
    for md in src_root.rglob("*.md"):
        front, _ = split_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
        rel = str(md.relative_to(src_root)).replace("\\", "/")
        title_of_file[rel] = str(front.get("title") or md.stem)

    out: dict[str, str] = {}
    for meta in store.iter_subtree():
        if meta.kind != "page":
            continue
        page = store.page(meta.id)
        ref = (page.source_ref or "").replace("\\", "/")
        if ref in title_of_file:
            out[meta.id] = title_of_file[ref]
    return out


def build(
    store: LibraryStore, catalog: Catalog, *, llm: LLM | None = None, progress=None
) -> dict[str, _Index]:
    llm = llm or get_llm()

    def note(msg: str) -> None:
        if progress:
            progress(msg)

    matrix, rows = catalog.vectors()
    q_page = np.array([r["page_id"] for r in rows])
    page_ids = sorted(catalog.page_ids())

    note(f"embedding {len(page_ids):,} page bodies")
    bodies = []
    for page_id in page_ids:
        page = store.page(page_id)
        bodies.append(f"{page.title}\n\n{page.markdown}"[:_MAX_CHARS])
    text_vecs = llm.embed(bodies)

    note("embedding sections")
    sec_texts: list[str] = []
    sec_page: list[str] = []
    for page_id in page_ids:
        page = store.page(page_id)
        for section in split_sections(page.markdown):
            body = section.body.strip()
            if body:
                sec_texts.append(f"{page.title} — {section.title}\n\n{body}"[:_MAX_CHARS])
                sec_page.append(page_id)
    sec_vecs = llm.embed(sec_texts)
    note(f"  {len(sec_texts):,} sections")

    return {
        "questions": _Index(matrix, q_page, page_ids),
        "text": _Index(text_vecs, np.array(page_ids), page_ids),
        "sections": _Index(sec_vecs, np.array(sec_page), page_ids),
    }


def score(
    indexes: dict[str, _Index],
    queries: list[Query],
    article_of: dict[str, str],
    *,
    llm: LLM | None = None,
    progress=None,
) -> list[MultihopRow]:
    llm = llm or get_llm()
    if progress:
        progress(f"embedding {len(queries):,} ground-truth questions")
    q_vecs = llm.embed([q.text for q in queries], task="RETRIEVAL_QUERY")

    kinds = ["all", *sorted({q.kind for q in queries})]
    acc: dict[tuple[str, str], dict] = {
        (name, kind): {
            "n": 0,
            "hit": dict.fromkeys(KS, 0.0),
            "cov": dict.fromkeys(KS, 0.0),
            "all": dict.fromkeys(KS, 0.0),
        }
        for name in INDEXES
        for kind in kinds
    }

    for qi, query in enumerate(queries):
        ranked: dict[str, list[str]] = {}
        for name in ("questions", "text", "sections"):
            ranked[name] = indexes[name].rank(q_vecs[qi])
        # RRF, not max-pool: a question↔question cosine and a question↔text cosine are not on one
        # scale, and pooling them by score lets the questions win every tie by construction.
        ranked["both"] = fuse([ranked["questions"], ranked["text"]])

        for name in INDEXES:
            # A page is only a lead to its ARTICLE — several pages of one article are one hit, so
            # `top k` counts DISTINCT articles, which is also what a reader is given.
            articles: list[str] = []
            for page_id in ranked[name]:
                title = article_of.get(page_id)
                if title and title not in articles:
                    articles.append(title)
                if len(articles) >= max(KS):
                    break
            for kind in ("all", query.kind):
                cell = acc[(name, kind)]
                cell["n"] += 1
                for k in KS:
                    found = set(articles[:k]) & query.gold
                    cell["hit"][k] += 1.0 if found else 0.0
                    cell["cov"][k] += len(found) / len(query.gold)
                    cell["all"][k] += 1.0 if len(found) == len(query.gold) else 0.0

    out: list[MultihopRow] = []
    for name in INDEXES:
        for kind in kinds:
            cell = acc[(name, kind)]
            n = max(cell["n"], 1)
            out.append(
                MultihopRow(
                    index=name,
                    kind=kind,
                    n=cell["n"],
                    hit={k: cell["hit"][k] / n for k in KS},
                    coverage={k: cell["cov"][k] / n for k in KS},
                    allgold={k: cell["all"][k] / n for k in KS},
                )
            )
    return out
