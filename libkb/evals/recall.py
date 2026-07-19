"""Recall@k: embedding is a bad ORACLE and a good SIEVE. Measure it (§7). ZERO LLM calls.

The leave-intent-out probe found dense top-1 page accuracy of **39.3%** on questions the ingest-time
generator never anticipated, and that was read as "the catalog is near-useless". **That is a
precision number being used to condemn a recall job.** A shortlister does not have to be right on
the first try — it only has to keep the answer inside the top-k and hand those k to the LLM, which
does the precision work (the two-stage self-reduction → contrastive-compare recipe, Lu et al. 2024).

Two regimes, same machinery as `catalog_probe.py`:
  LOO  drop the query's own row      ⇒ "a paraphrase of a question we DID anticipate"
  LOI  drop its whole intent (vi+en) ⇒ "an intent we NEVER anticipated"  ← the honest, hard case

And two poolings, because **a container is a union of topics, not one topic**:
  mean  the centroid of a 5-topic book sits in empty space, resembling nothing it holds
  max   "does this book CONTAIN anything close to the query?" — the question actually being asked

Container vectors cost **zero** new API calls: they are pooled from page vectors already stored.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from libkb.catalog.store import Catalog

KS = (1, 3, 5, 10, 20)


@dataclass
class RecallRow:
    level: str  # page | book | shelf
    regime: str  # LOO | LOI
    pooling: str  # max | mean
    n_targets: int  # how many candidates existed at this level (a 3-of-6 recall is a weak test)
    at_k: dict[int, float] = field(default_factory=dict)


def probe_recall(catalog: Catalog) -> list[RecallRow]:
    matrix, rows = catalog.vectors()
    n = len(rows)
    if n < 3:
        return []

    page = np.array([r["page_id"] for r in rows])
    book = np.array([r["book_id"] for r in rows])
    shelf = np.array(
        [
            " ▸ ".join(p.strip() for p in r["path"].split("▸")[:-2])
            if len(r["path"].split("▸")) >= 3
            else "(root)"
            for r in rows
        ]
    )

    # rows are written intent1.vi, intent1.en, intent2.vi, … per page (ingest/questions.py)
    seen: dict[str, int] = defaultdict(int)
    intent = np.empty(n, dtype=int)
    for i, r in enumerate(rows):
        intent[i] = seen[r["page_id"]] // 2
        seen[r["page_id"]] += 1

    sims = matrix @ matrix.T  # L2-normalised ⇒ cosine
    np.fill_diagonal(sims, -1.0)  # a question may never retrieve itself

    out: list[RecallRow] = []
    for level, labels in (("page", page), ("book", book), ("shelf", shelf)):
        groups = _group(labels)
        for regime, drop_intent in (("LOO", False), ("LOI", True)):
            for pooling in ("max", "mean"):
                if level == "page" and pooling == "mean":
                    continue  # a page IS one topic; pooling its own questions by mean is noise
                out.append(
                    _recall(level, regime, pooling, sims, labels, groups, page, intent, drop_intent)
                )

    # Does BM25 actually earn its place? Same held-out masking, fused by reciprocal rank (§7.3).
    lex = _lexical_matrix(catalog, rows)
    if lex is not None:
        for level, labels in (("page", page), ("book", book), ("shelf", shelf)):
            groups = _group(labels)
            for regime, drop_intent in (("LOO", False), ("LOI", True)):
                out.append(
                    _recall(
                        level,
                        regime,
                        "hybrid",
                        sims,
                        labels,
                        groups,
                        page,
                        intent,
                        drop_intent,
                        lexical=lex,
                    )
                )
    return out


def _lexical_matrix(catalog: Catalog, rows: list) -> np.ndarray | None:
    """(N, N) BM25 scores: entry [i, j] = how well row j matches row i's text as a query.

    Dense-only catalogs (no FTS5 build) return None and the hybrid rows are simply not reported.
    """
    ids = [r["id"] for r in rows]
    index_of = {row_id: i for i, row_id in enumerate(ids)}
    n = len(rows)
    lex = np.full((n, n), -np.inf, dtype=np.float32)
    any_hit = False
    for i, r in enumerate(rows):
        scores = catalog.lexical_row_scores(r["text"])
        for row_id, score in scores.items():
            j = index_of.get(row_id)
            if j is not None:
                lex[i, j] = score
                any_hit = True
    return lex if any_hit else None


RRF_K = 60


def _fuse(
    dense: np.ndarray,
    lex: np.ndarray,
    mask: np.ndarray,
    keys: list[str],
    groups: dict[str, np.ndarray],
) -> list[str]:
    """Rank containers by dense, rank them by BM25, fuse by reciprocal rank (§7.3).

    By RANK, not by score: cosines crowd into 0.87–0.90 and BM25 lives on an unrelated scale, so a
    weighted sum would be calibrating noise. RRF only asks how near the top each ranker put it.
    """
    lex = lex.copy()
    lex[mask] = -np.inf  # the held-out rows must not vote lexically either

    def rank(scores: np.ndarray, floor: float) -> list[str]:
        out: list[tuple[float, str]] = []
        for key in keys:
            live = scores[groups[key]]
            live = live[live > floor]
            if live.size:
                out.append((float(live.max()), key))  # a container is a union → max
        out.sort(reverse=True)
        return [key for _, key in out]

    fused: dict[str, float] = {}
    for ranking in (rank(dense, -1.0), rank(lex, -np.inf)):
        for position, key in enumerate(ranking, start=1):
            fused[key] = fused.get(key, 0.0) + 1.0 / (RRF_K + position)
    return sorted(fused, key=lambda key: fused[key], reverse=True)


def _group(labels: np.ndarray) -> dict[str, np.ndarray]:
    groups: dict[str, list[int]] = defaultdict(list)
    for i, key in enumerate(labels):
        groups[key].append(i)
    return {k: np.asarray(v) for k, v in groups.items()}


def _recall(
    level: str,
    regime: str,
    pooling: str,
    sims: np.ndarray,
    labels: np.ndarray,
    groups: dict[str, np.ndarray],
    page: np.ndarray,
    intent: np.ndarray,
    drop_intent: bool,
    lexical: np.ndarray | None = None,
) -> RecallRow:
    n = sims.shape[0]
    keys = list(groups)
    hits = {k: 0 for k in KS}
    counted = 0

    for i in range(n):
        s = sims[i].copy()
        mask = (page == page[i]) & (intent == intent[i]) if drop_intent else np.arange(n) == i
        s[mask] = -1.0

        if pooling == "hybrid" and lexical is not None:
            ranked = _fuse(s, lexical[i], mask, keys, groups)
        else:
            scored: list[tuple[float, str]] = []
            for key in keys:
                idx = groups[key]
                live = s[idx]
                live = live[live > -1.0]  # rows we removed do not get to vote
                if live.size == 0:
                    continue
                scored.append((float(live.max() if pooling == "max" else live.mean()), key))
            scored.sort(reverse=True)
            ranked = [key for _, key in scored]
        if len(ranked) < 2:
            continue
        truth = labels[i]
        counted += 1
        for k in KS:
            if truth in ranked[:k]:
                hits[k] += 1

    return RecallRow(
        level=level,
        regime=regime,
        pooling=pooling,
        n_targets=len(keys),
        at_k={k: (hits[k] / counted if counted else 0.0) for k in KS},
    )
