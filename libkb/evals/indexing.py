"""WHAT should the sieve index: the page's QUESTIONS, or the page's TEXT? (D-039)

The user's challenge, and it is the oldest unexamined assumption in the project: *"four generated
questions cannot cover the space of natural questions, let alone synthesis questions."* He is right,
and our own numbers have been saying so from the beginning without anyone naming it:

    LOO  a paraphrase of a question we DID anticipate ......... 86.2%
    LOI  an intent we NEVER anticipated ...................... 56.1%   ← the 30-point hole

**That 30-point gap IS the cost of indexing generated questions.** D-005 justified the choice by
symmetry (a reader asks a question; question-to-question is an aligned comparison), but we never
measured it against the obvious alternative — while in the same project we refuted NMS, BM25, the
page digest and `routing_mode=auto` with measurement. And the symmetry argument contradicts itself:
gemini-embedding-001 is *built* for asymmetric retrieval (`RETRIEVAL_DOCUMENT` vs
`RETRIEVAL_QUERY`), and we are using the document task type to embed... questions.

It is also now an economic question, not only an accuracy one. Question-indexing costs one LLM call
per page. On a 22,633-article legal code that is ~34M generated tokens; text-indexing costs zero
generation. **The flywheel simply cannot survive a real corpus.** So this probe decides whether a
large corpus is reachable at all.

Four indexes, same pages, same queries, same truth:

    questions  what we ship today — the generated questions (+ entry terms)
    text       the page body, embedded directly. Zero LLM calls.
    sections   each section embedded separately; a page scores as its best section (finer, and it is
               the same unit the cascade already READS by)
    both       questions ∪ text, max-pooled per page — the hypothesis that they are complementary,
               not rivals: questions carry the reader's vocabulary, text carries everything the page
               actually says

NOTE ON COST: this probe makes **no generation calls at all**. It re-uses the catalog's existing
question vectors and embeds page/section text. Embeddings are ~an order of magnitude cheaper than
generation, which is the entire point being tested.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import structlog

from libkb.catalog.store import Catalog
from libkb.library.sections import split_sections
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)

KS = (1, 3, 10)
_MAX_PAGE_CHARS = 8000  # the embedder truncates anyway; be explicit about where
INDEXES = ("questions", "text", "sections", "both")


@dataclass
class IndexRow:
    index: str
    regime: str  # LOI | holdout
    n_queries: int
    n_vectors: int  # how many rows the sieve holds — the thing you pay to store and scan
    at_k: dict[int, float] = field(default_factory=dict)


RRF_K = 60


@dataclass
class _Index:
    """Vectors, and which page each one belongs to. A page scores as its BEST row — the same
    'a container is a union of topics' rule the live lookup uses."""

    vectors: np.ndarray
    page_of_row: np.ndarray
    pages: list[str]

    def scores(self, q: np.ndarray, drop: np.ndarray | None = None) -> dict[str, float]:
        sims = self.vectors @ q
        if drop is not None:
            sims = np.where(drop, -1.0, sims)
        best: dict[str, float] = {}
        for score, page_id in zip(sims, self.page_of_row, strict=True):
            if score > -1.0 and score > best.get(page_id, -2.0):
                best[page_id] = float(score)
        return best

    def rank(self, q: np.ndarray, drop: np.ndarray | None = None) -> list[str]:
        best = self.scores(q, drop)
        return sorted(best, key=lambda p: best[p], reverse=True)


def fuse(rankings: list[list[str]]) -> list[str]:
    """Reciprocal-rank fusion — and the reason it is not a max-pool is a bug we already made once.

    Stacking question-vectors and text-vectors and taking the best cosine per page LOOKS like a
    union. It is not: a question-to-QUESTION cosine is systematically higher than a
    question-to-TEXT cosine, because the two are different kinds of comparison on different scales.
    Max-pooling therefore lets the question rows win every tie by construction, and `both` came out
    byte-identical to `questions` — the text side was never consulted at all.

    RRF asks only *how near the top each index put this page*, which needs no shared scale. It is
    the same reasoning as §7.3's BM25 fusion, and we forgot it inside a week.
    """
    fused: dict[str, float] = {}
    for ranking in rankings:
        for position, page_id in enumerate(ranking, start=1):
            fused[page_id] = fused.get(page_id, 0.0) + 1.0 / (RRF_K + position)
    return sorted(fused, key=lambda p: fused[p], reverse=True)


def build_indexes(
    store: LibraryStore, catalog: Catalog, *, llm: LLM | None = None, progress=None
) -> tuple[dict[str, _Index], list[str], np.ndarray, np.ndarray]:
    """Returns the four indexes plus the catalog's own rows (used as the LOI query set)."""
    llm = llm or get_llm()

    def note(msg: str) -> None:
        if progress:
            progress(msg)

    matrix, rows = catalog.vectors()
    q_page = np.array([r["page_id"] for r in rows])
    # rows are written intent1.vi, intent1.en, intent2.vi, … (ingest/questions.py)
    seen: dict[str, int] = defaultdict(int)
    q_intent = np.empty(len(rows), dtype=int)
    for i, r in enumerate(rows):
        q_intent[i] = seen[r["page_id"]] // 2
        seen[r["page_id"]] += 1

    page_ids = sorted(catalog.page_ids())
    note(f"embedding {len(page_ids)} page bodies")
    bodies: list[str] = []
    for page_id in page_ids:
        page = store.page(page_id)
        bodies.append(f"{page.title}\n\n{page.markdown}"[:_MAX_PAGE_CHARS])
    text_vecs = llm.embed(bodies)  # RETRIEVAL_DOCUMENT — what the task type is actually FOR

    note("embedding sections")
    sec_texts: list[str] = []
    sec_page: list[str] = []
    for page_id in page_ids:
        page = store.page(page_id)
        for section in split_sections(page.markdown):
            body = section.body.strip()
            if body:
                sec_texts.append(f"{page.title} — {section.title}\n\n{body}"[:_MAX_PAGE_CHARS])
                sec_page.append(page_id)
    sec_vecs = llm.embed(sec_texts)
    note(f"  {len(sec_texts)} sections")

    q_index = _Index(matrix, q_page, page_ids)
    t_index = _Index(text_vecs, np.array(page_ids), page_ids)
    s_index = _Index(sec_vecs, np.array(sec_page), page_ids)
    b_index = _Index(
        np.vstack([matrix, text_vecs]),
        np.concatenate([q_page, np.array(page_ids)]),
        page_ids,
    )
    indexes = {"questions": q_index, "text": t_index, "sections": s_index, "both": b_index}
    return indexes, list(q_page), matrix, q_intent


def probe_indexes(
    store: LibraryStore,
    catalog: Catalog,
    *,
    holdout: list[tuple[str, str]] | None = None,
    llm: LLM | None = None,
    progress=None,
) -> list[IndexRow]:
    """`holdout` is (query, target_page_id) — colloquial paraphrases a reader would actually type.
    The LOI regime runs regardless; it is free (the vectors are already in the catalog)."""
    llm = llm or get_llm()
    indexes, q_page, q_vecs, q_intent = build_indexes(store, catalog, llm=llm, progress=progress)
    out: list[IndexRow] = []

    # ---- LOI: query = a stored question; its whole intent (vi+en) is removed from the index that
    # contains it. For the text/section indexes there is nothing to remove — the text was never a
    # question — which is precisely the asymmetry under test.
    q_page_arr = np.array(q_page)
    for name in INDEXES:
        index = indexes[name]
        hits = {k: 0 for k in KS}
        for i in range(len(q_page)):
            drop = None
            if name in ("questions", "both"):
                same = (q_page_arr == q_page_arr[i]) & (q_intent == q_intent[i])
                # `both` stacks [questions ; text], so the mask must be padded to the text rows
                pad = len(index.page_of_row) - len(same)
                drop = np.concatenate([same, np.zeros(pad, dtype=bool)]) if pad else same
            ranked = index.rank(q_vecs[i], drop)
            for k in KS:
                if q_page_arr[i] in ranked[:k]:
                    hits[k] += 1
        out.append(
            IndexRow(
                index=name,
                regime="LOI",
                n_queries=len(q_page),
                n_vectors=len(index.page_of_row),
                at_k={k: hits[k] / len(q_page) for k in KS},
            )
        )

    # ---- HELD-OUT: the honest regime. Real paraphrases, nothing to mask, no leak anywhere.
    if holdout:
        texts = [q for q, _ in holdout]
        targets = [t for _, t in holdout]
        vecs = llm.embed(texts, task="RETRIEVAL_QUERY")
        for name in INDEXES:
            index = indexes[name]
            hits = {k: 0 for k in KS}
            for i, target in enumerate(targets):
                ranked = index.rank(vecs[i])
                for k in KS:
                    if target in ranked[:k]:
                        hits[k] += 1
            out.append(
                IndexRow(
                    index=name,
                    regime="holdout",
                    n_queries=len(targets),
                    n_vectors=len(index.page_of_row),
                    at_k={k: hits[k] / len(targets) for k in KS},
                )
            )
    return out
