"""Query-side catalog lookup: embed a question, rank pages, apply an optional threshold.

Three callers. Two are *gates* and use `min_margin` (D-028): the orchestrator's fast path (answer
without walking) and the navigator's `ask_librarian` tool.

The third is a **sieve**, and it deliberately uses no gate at all (§7.3): the shelf shortlist, which
narrows a shelf too wide to render into ~5 candidates the librarian then compares for himself.
Score compression (everything crowds at 0.87–0.90) makes an absolute threshold meaningless there —
but it does not touch the RANKING, which is all a shortlist needs. Do not reintroduce a threshold on
that path; a shortlister is allowed to be unsure, because the LLM does the precision work.
"""

from __future__ import annotations

from libkb.catalog.store import Catalog, Hit
from libkb.config import get_settings
from libkb.llm.client import LLM, get_llm


def lookup(
    catalog: Catalog,
    query: str,
    *,
    llm: LLM | None = None,
    top_k: int | None = None,
    threshold: float | None = None,
    min_margin: float | None = None,
    within: set[str] | None = None,
) -> list[Hit]:
    """Embed `query` (as a retrieval query) and return the best distinct pages.

    `threshold` is a weak absolute floor. `min_margin` is the REAL confidence gate (D-028): the
    best page must beat the runner-up PAGE by at least this cosine margin, otherwise the match is
    ambiguous and we return nothing so the librarian walks instead. When the margin gate passes,
    only the winning page is returned — that is the case the precision numbers were measured on.

    `within` restricts candidates to a set of page_ids (the shelf shortlist).
    """
    llm = llm or get_llm()
    top_k = top_k or get_settings().catalog_top_k
    query_vec = llm.embed([query], task="RETRIEVAL_QUERY")[0]
    hits = catalog.search(query_vec, top_k=top_k, within=within)
    if threshold is not None:
        hits = [h for h in hits if h.score >= threshold]
    if min_margin is not None and hits:
        runner_up = hits[1].score if len(hits) > 1 else 0.0
        if hits[0].score - runner_up < min_margin:
            return []  # too close to call — the walk is more reliable than a coin flip
        return [hits[0]]
    return hits


RRF_K = 60  # the standard constant; large enough that rank-1 does not dominate outright


def hybrid_lookup(
    catalog: Catalog,
    query: str,
    *,
    llm: LLM | None = None,
    top_k: int | None = None,
    within: set[str] | None = None,
) -> list[Hit]:
    """Dense + lexical, fused by reciprocal rank (§7.3). This is the SIEVE — no gate, by design.

    Dense retrieval smears rare terms and named entities (HNSW, GMROI, a SKU code, a Japanese retail
    term) into whatever neighbourhood it learned at training time. BM25 matches them exactly. Each
    covers the other's blind spot.

    Fusion is by RANK, never by score: cosines here crowd into 0.87–0.90 (D-028) and BM25 scores are
    on an unrelated scale, so any weighted-sum fusion would be calibrating noise. RRF needs no
    calibration — it only asks "how near the top did each ranker put this page?".

    Degrades cleanly: no FTS5 build, or a query with no usable terms ⇒ the dense ranking, unchanged.
    """
    llm = llm or get_llm()
    top_k = top_k or get_settings().catalog_top_k

    dense = lookup(catalog, query, llm=llm, top_k=top_k * 2, within=within)
    lexical = catalog.search_lexical(query, top_k=top_k * 2, within=within)
    if not lexical:
        return dense[:top_k]

    scores: dict[str, float] = {}
    hit_of: dict[str, Hit] = {}
    for ranking in (dense, lexical):
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.page_id] = scores.get(hit.page_id, 0.0) + 1.0 / (RRF_K + rank)
            hit_of.setdefault(hit.page_id, hit)  # keep the dense hit's text/score for display

    ordered = sorted(scores, key=lambda pid: scores[pid], reverse=True)[:top_k]
    return [hit_of[pid] for pid in ordered]
