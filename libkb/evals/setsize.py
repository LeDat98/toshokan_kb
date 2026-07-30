"""How MANY candidates to keep — decided per query, from the sieve's own scores, with NO model call.

Both selectors here attack one measured fact. The true-page set is **2.75 documents on average and
its size moves with the question** (comparison 2.25 · temporal 2.49 · inference 3.46), while every
selector we have measured commits to a near-constant **3.0-3.2**. A constant cannot be a superset of
a variable target: on the kinds that need four documents it is short by one before the model has
judged anything. That failure is arithmetic, not judgement — so the fix should not need a model.

Two published ways to make the size vary, both training-free and both free to measure here:

    adaptive_k    cut the ranked list at its sharpest score drop, then take a fixed buffer more.
                  (Adaptive-k, arXiv 2506.08479 — "no tuning, no iteration")
    conformal     calibrate ONE threshold on labelled queries such that the kept set contains every
                  true page on at least (1-alpha) of queries, then apply it unchanged.
                  (Conformal filtering, arXiv 2511.17908)

**Why conformal is the interesting one.** `docs/SELECTION_TARGET.md` sets the goal as *superset >=
90%*. That is not a heuristic target — it is exactly a conformal coverage level, 1-alpha = 0.90, and
conformal prediction is the procedure that attains a stated coverage at the smallest threshold that
attains it, with a finite-sample guarantee and no distributional assumption. So this arm does not
merely try to do well on the metric; it optimises the metric by construction. What it then costs in
`taken` and `ctx_tokens` is the honest price of the 90% target, measured rather than argued.

**The adaptation that matters.** Textbook conformal filtering certifies that an average RELEVANT
SNIPPET is retained — a per-document guarantee. Our objective is per-QUERY and set-valued: every
member of TP, or the query is a miss. So the nonconformity score here is not a document's score but
**the worst score among that query's gold documents** — the threshold each query would have needed
to keep all of them. Calibrating on that quantity certifies `superset` directly. (Calibrating on
individual gold documents would certify (1-alpha) per document, i.e. roughly (1-alpha)^|TP| per
query — 73% where we want 90%.)

**The control this arm must beat, and it is not optional.** Both selectors here choose a set SIZE
from scores; neither reads a page. If either matches `embedder` taking the same average number of
pages, then the adaptivity added nothing and the win was budget (metric bug 6.8, SELECTION_TARGET
rule 2). `probe-selection` runs that matched control automatically for exactly this reason.

Everything in this module is pure: lists of floats in, indices out. No LLM, no store, no I/O.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

# Adaptive-k's buffer B: after the sharpest drop, take a few more anyway. The paper uses 5, and the
# reason it exists is our failure mode — the drop marks where the ranking gets vague, not where the
# evidence ends, and a multi-hop question's later hops routinely sit past it.
DEFAULT_BUFFER = 5

# Gaps are searched over the top of the list only. The last few positions of any ranked list have a
# large, meaningless drop into the tail; without this the argmax lands there on nearly every query.
DEFAULT_SEARCH_FRAC = 0.9

# 1 - alpha is the target `superset`. 0.10 because docs/SELECTION_TARGET.md asks for >= 90%.
DEFAULT_ALPHA = 0.10

# Cross-fitting folds. A threshold must never be applied to a query that helped calibrate it, or the
# arm scores its own training data — and every query still gets scored, so `n` matches every other
# arm and the comparison stays legal.
DEFAULT_FOLDS = 5


def adaptive_k(
    scores: Sequence[float],
    *,
    buffer: int = DEFAULT_BUFFER,
    search_frac: float = DEFAULT_SEARCH_FRAC,
) -> int:
    """Adaptive-k: keep everything above the sharpest drop in the sorted scores, plus `buffer`.

    `scores` must be descending (what `catalog.search` returns). Returns how many to keep, at least
    1 — an empty basket is the one outcome strictly worse than every alternative (D-035).
    """
    n = len(scores)
    if n <= 1:
        return n
    # Gaps are the differences WITHIN the top `search_frac` of the list, so the last considered gap
    # is the one between its final two members: keeping m documents leaves m-1 interior gaps. Off by
    # one here and the tail cliff is back inside the search, which is the failure the horizon exists
    # to prevent.
    horizon = max(1, min(int(n * search_frac) - 1, n - 1))
    gaps = [scores[i] - scores[i + 1] for i in range(horizon)]
    # argmax with first-wins on ties (numpy's semantics, and the paper's). A tie means two equally
    # sharp drops; taking the earlier one is the smaller basket, and the buffer is what protects it.
    cut = max(range(len(gaps)), key=gaps.__getitem__)
    return max(1, min(n, cut + 1 + buffer))


def margins(scores: Sequence[float]) -> list[float]:
    """Nonconformity: how far below the query's OWN best each candidate sits.

    Raw cosine is not comparable across queries — a query with an exact match tops out near 0.85, a
    vague one near 0.55, and a single global cutoff would take everything from the first and nothing
    from the second. The distance from that query's top-1 is comparable; that is what makes the
    conformal exchangeability assumption defensible here.
    """
    if not scores:
        return []
    top = max(scores)
    return [top - s for s in scores]


def required_margin(scores: Sequence[float], gold_ranks: Sequence[int]) -> float | None:
    """The smallest threshold that would have kept EVERY gold document for this query.

    None when a gold document is not in the pool at all: that is a sieve failure (the `ceiling`,
    92.7% here), and letting it into the calibration would push the threshold to infinity to fix
    something no threshold can fix.
    """
    if not gold_ranks:
        return None
    ms = margins(scores)
    worst = 0.0
    for rank in gold_ranks:
        if rank < 0 or rank >= len(ms):
            return None
        worst = max(worst, ms[rank])
    return worst


def conformal_quantile(required: Sequence[float], alpha: float = DEFAULT_ALPHA) -> float:
    """The split-conformal threshold: the ceil((n+1)(1-alpha))-th smallest calibration score.

    The `+1` is the finite-sample correction, and it is the whole guarantee — with it, a fresh
    exchangeable query is covered with probability >= 1-alpha for ANY n, with no assumption about
    how the scores are distributed. When ceil((n+1)(1-alpha)) exceeds n the sample is simply too
    small to certify the level, and the honest return is infinity — keep the whole pool — rather
    than the largest value on hand, which would quietly certify a weaker level than was asked for.
    """
    vals = sorted(v for v in required if v is not None and math.isfinite(v))
    n = len(vals)
    if n == 0:
        return math.inf
    idx = math.ceil((n + 1) * (1.0 - alpha))
    if idx > n:
        return math.inf
    return vals[idx - 1]


def conformal_keep(scores: Sequence[float], threshold: float) -> list[int]:
    """Indices of every candidate within `threshold` of the top-1. Never empty (D-035)."""
    if not scores:
        return []
    if not math.isfinite(threshold):
        return list(range(len(scores)))
    ms = margins(scores)
    kept = [i for i, m in enumerate(ms) if m <= threshold + 1e-12]
    return kept or [max(range(len(scores)), key=scores.__getitem__)]


def kfold(n: int, folds: int = DEFAULT_FOLDS, seed: int = 11) -> list[int]:
    """Deterministic fold assignment, balanced to within one item. Seeded, so a re-run of the probe
    reproduces the same thresholds and two arms remain comparable across sessions."""
    if n <= 0:
        return []
    folds = max(1, min(folds, n))
    assign = [i % folds for i in range(n)]
    random.Random(seed).shuffle(assign)
    return assign


def cross_fit_thresholds(
    required: Sequence[float | None],
    *,
    alpha: float = DEFAULT_ALPHA,
    folds: int = DEFAULT_FOLDS,
    seed: int = 11,
) -> list[float]:
    """One threshold per query, each calibrated on the OTHER folds only.

    Split-conformal would hold out a calibration set and score the rest, which costs `n` and makes
    this arm incomparable to every other arm in the probe. Cross-fitting scores every query under a
    threshold that never saw it, so `n` is identical across arms and nothing is scored on itself.
    """
    n = len(required)
    if n == 0:
        return []
    assign = kfold(n, folds, seed)
    by_fold = {
        f: conformal_quantile(
            [required[j] for j in range(n) if assign[j] != f and required[j] is not None], alpha
        )
        for f in set(assign)
    }
    return [by_fold[assign[i]] for i in range(n)]
