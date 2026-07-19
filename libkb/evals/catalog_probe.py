"""Held-out probe of the card catalog: does it GENERALISE, or only match its own rows?

**Zero LLM calls** — pure cosine over vectors already stored, so it is free to re-run whenever
the corpus changes. Two simulations of a real user (D-028):

  LOO  drop the query's own row; the page keeps its other questions.
       ⇒ "the user paraphrases a question we did index."
  LOI  drop the query's row AND its translation twin (same page, same intent).
       ⇒ "the user asks about the page in a way we never thought of."

For each candidate gate it reports how often the shortcut FIRES and how precise it is when it
does. The headline finding: the ABSOLUTE cosine is not a usable confidence signal (scores crowd
near 0.9, so any workable floor fires on ~everything), while the MARGIN between the best page
and the runner-up page separates cleanly. `est_e2e` conservatively scores a fired-but-wrong hit
as lost, and a silent gate as falling back to the walk.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from libkb.catalog.store import Catalog

WALK_ACC = 0.86  # measured leak-free walk accuracy — what we fall back to when the gate is silent
MARGINS = (0.0, 0.01, 0.02, 0.03, 0.05, 0.08)
THRESHOLDS = (0.80, 0.85, 0.90, 0.95)


@dataclass
class GateRow:
    value: float
    fires: float
    precision: float
    est_e2e: float


@dataclass
class ProbeResult:
    label: str
    n: int
    top1_page_acc: float  # ignoring any gate
    median_score: float
    median_margin: float
    by_margin: list[GateRow] = field(default_factory=list)
    by_threshold: list[GateRow] = field(default_factory=list)


def probe(catalog: Catalog, *, walk_acc: float = WALK_ACC) -> list[ProbeResult]:
    matrix, rows = catalog.vectors()
    n = len(rows)
    if n < 3:
        return []
    pages = np.array([r["page_id"] for r in rows])

    # rows were written intent1.vi, intent1.en, intent2.vi, … per page (see ingest/questions.py)
    seen: dict[str, int] = defaultdict(int)
    intent = np.empty(n, dtype=int)
    for i, r in enumerate(rows):
        intent[i] = seen[r["page_id"]] // 2
        seen[r["page_id"]] += 1

    sims = matrix @ matrix.T  # both sides L2-normalised ⇒ cosine
    np.fill_diagonal(sims, -1.0)  # a question may never match itself

    def run(label: str, drop_twin: bool) -> ProbeResult:
        top_score = np.empty(n)
        margin = np.empty(n)
        correct = np.zeros(n, dtype=bool)
        for i in range(n):
            s = sims[i].copy()
            if drop_twin:
                s[(pages == pages[i]) & (intent == intent[i])] = -1.0
            j = int(np.argmax(s))
            winner = pages[j]
            top_score[i] = s[j]
            correct[i] = winner == pages[i]
            others = s.copy()
            others[pages == winner] = -1.0  # best score from any OTHER page
            margin[i] = s[j] - others.max()

        def gate(mask: np.ndarray, value: float) -> GateRow:
            fires = float(mask.mean())
            precision = float(correct[mask].mean()) if mask.any() else 0.0
            return GateRow(
                value=value,
                fires=fires,
                precision=precision,
                est_e2e=fires * precision + (1 - fires) * walk_acc,
            )

        return ProbeResult(
            label=label,
            n=n,
            top1_page_acc=float(correct.mean()),
            median_score=float(np.median(top_score)),
            median_margin=float(np.median(margin)),
            by_margin=[gate(margin >= d, d) for d in MARGINS],
            by_threshold=[gate(top_score >= t, t) for t in THRESHOLDS],
        )

    return [
        run("LOO — user paraphrases a question we indexed", drop_twin=False),
        run("LOI — user asks something we never thought of", drop_twin=True),
    ]
