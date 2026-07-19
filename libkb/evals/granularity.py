"""Which leaf granularity does THIS corpus want? Measure it; do not pick it (D-037).

The premise, borrowed from Ekimetrics' `adaptive-chunking`: no single cut is right for every
document, so run a verify metric and let the corpus choose. We take their **loop** and refuse their
**metric**. Their five intrinsic scores (size compliance, intra-chunk cohesion, block integrity…)
all measure whether a chunk LOOKS well-formed. Ours measures whether the librarian FINDS it. Three
times in this project the broken thing turned out to be the metric and not the system (D-035); a
proxy is the last thing we need another of.

Two axes, because leaf size pulls them in opposite directions and only one of them is ever quoted:

    RECALL   finer leaves ⇒ more competitors in the sieve ⇒ the right one is harder to rank
    READING  coarser leaves ⇒ the answerer is handed more text it did not ask for

A chunker that wins on recall by making the library one enormous page has not won anything. So both
are reported, plus the failure mode the user actually fears at scale: **near-duplicate flood** — the
share of leaves that sit within a hair of a leaf from a DIFFERENT document, i.e. the candidates that
will crowd each other out of the shortlist once the corpus is big.

**Fairness.** Comparing recall across strategies is a trap: a coarser cut has fewer leaves, so it
scores higher for free. We defuse it by fixing the ground truth OUTSIDE the cut. The truth of a
query is the SOURCE FILE it was generated from — a unit no strategy is allowed to redefine — and a
strategy is correct when any leaf it derived from that file lands in the top-k. Same queries, same
truth, different indexes.

**Caveat we do not hide.** The queries are generated from the same text they index, so these numbers
are a LOO regime (a paraphrase of an anticipated question), not the LOI regime that produced our
honest 39.3%. They are comparable to EACH OTHER, which is the only claim being made.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import structlog

from libkb.config import get_settings
from libkb.ingest.frontmatter import split_frontmatter
from libkb.ingest.split import bound_page, is_apparatus
from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)

KS = (1, 3, 10)
_TOP_READ = 3  # the cascade opens a basket of 3 (config.cascade_max_pages)


@dataclass(frozen=True)
class Strategy:
    name: str
    max_tokens: int
    min_chars: int


def default_strategies(settings=None) -> list[Strategy]:
    s = settings or get_settings()
    return [
        Strategy("as-authored", max_tokens=10**6, min_chars=0),  # never cut a file: the control
        Strategy("tight", max_tokens=500, min_chars=s.split_min_page_chars),
        Strategy("medium", max_tokens=1000, min_chars=s.split_min_page_chars),
        Strategy("default", max_tokens=s.split_max_page_tokens, min_chars=s.split_min_page_chars),
    ]


@dataclass
class SourceFile:
    file_id: str
    title: str
    body: str


@dataclass
class Leaf:
    file_id: str  # the ground truth: which document this text came from
    title: str
    text: str

    @property
    def tokens(self) -> int:
        return len(self.text) // 4

    @property
    def key(self) -> str:
        return hashlib.sha1(self.text.encode("utf-8")).hexdigest()  # noqa: S324 — a cache key


@dataclass
class GranularityRow:
    strategy: str
    n_leaves: int
    median_tokens: int
    p95_tokens: int
    read_tokens: int  # what the answerer pays for a basket of 3 — the cost axis
    margin: float  # mean (score@1 − score@10): how sharply the sieve separates. Small = FLOOD.
    at_k: dict[int, float] = field(default_factory=dict)
    new_calls: int = 0


def read_source(folder: str | Path, limit: int | None = None) -> list[SourceFile]:
    """Every .md under `folder`, recursively. The FILE is the unit of truth."""
    root = Path(folder)
    files: list[SourceFile] = []
    for md in sorted(root.rglob("*.md")):
        front, body = split_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
        body = body.strip()
        if not body:
            continue
        title = str(front.get("title") or md.stem).strip()
        files.append(SourceFile(str(md.relative_to(root)).replace("\\", "/"), title, body))
        if limit and len(files) >= limit:
            break
    return files


def cut(files: list[SourceFile], strategy: Strategy) -> list[Leaf]:
    leaves: list[Leaf] = []
    for f in files:
        pieces = bound_page(
            f.body, f.title, max_tokens=strategy.max_tokens, min_chars=strategy.min_chars
        )
        for i, (title, text) in enumerate(pieces):
            if not text.strip() or is_apparatus(title):
                continue
            name = title or f.title
            if len(pieces) > 1:
                name = f"{f.title} — {title}" if title else f"{f.title} ({i + 1})"
            leaves.append(Leaf(f.file_id, name, text.strip()))
    return leaves


class _Bank:
    """Questions + embeddings, cached by leaf CONTENT.

    Strategies overlap heavily — a small file is one leaf under every budget — so without this the
    sweep would pay for the same page four times. With it, a strategy costs only what is genuinely
    new about it, and the printed call count says exactly how much that was.
    """

    def __init__(self, llm: LLM, n: int) -> None:
        self.llm = llm
        self.n = n
        self._q: dict[str, list[str]] = {}
        self._v: dict[str, np.ndarray] = {}
        self.calls = 0

    def questions(self, leaf: Leaf) -> list[str]:
        from libkb.ingest.questions import generate_card

        if leaf.key not in self._q:
            card = generate_card(leaf.title, leaf.text, n=self.n, llm=self.llm)
            self._q[leaf.key] = [q.text for q in card.questions] or [leaf.title]
            self.calls += 1
        return self._q[leaf.key]

    def embed(self, texts: list[str]) -> np.ndarray:
        missing = [t for t in texts if t not in self._v]
        for i in range(0, len(missing), 64):
            batch = missing[i : i + 64]
            for text, vec in zip(batch, self.llm.embed(batch), strict=True):
                self._v[text] = np.asarray(vec, dtype=np.float32)
        return np.vstack([self._v[t] for t in texts])


def probe_granularity(
    files: list[SourceFile],
    strategies: list[Strategy],
    *,
    llm: LLM | None = None,
    progress=None,
) -> list[GranularityRow]:
    llm = llm or get_llm()
    settings = get_settings()
    bank = _Bank(llm, settings.questions_per_page)

    def note(msg: str) -> None:
        if progress:
            progress(msg)

    # THE QUERY SET — generated once, from the whole file, and never regenerated. Every strategy is
    # asked the same questions, or the comparison means nothing.
    note(f"building the query set from {len(files)} files")
    queries: list[str] = []
    truth: list[str] = []
    for f in files:
        leaf = Leaf(f.file_id, f.title, f.body)
        for q in bank.questions(leaf):
            queries.append(q)
            truth.append(f.file_id)
    q_vecs = bank.embed(queries)
    q_vecs /= np.linalg.norm(q_vecs, axis=1, keepdims=True) + 1e-9

    rows: list[GranularityRow] = []
    for strategy in strategies:
        before = bank.calls
        leaves = cut(files, strategy)
        note(f"{strategy.name}: {len(leaves)} leaves — indexing")

        leaf_rows: list[int] = []  # row → leaf index
        texts: list[str] = []
        for i, leaf in enumerate(leaves):
            for q in bank.questions(leaf):
                texts.append(q)
                leaf_rows.append(i)
        vecs = bank.embed(texts)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9

        rows.append(
            _score(
                strategy, leaves, np.asarray(leaf_rows), vecs, q_vecs, truth, bank.calls - before
            )
        )
    return rows


def _score(
    strategy: Strategy,
    leaves: list[Leaf],
    leaf_of_row: np.ndarray,
    vecs: np.ndarray,
    q_vecs: np.ndarray,
    truth: list[str],
    new_calls: int,
) -> GranularityRow:
    sims = q_vecs @ vecs.T  # (n_queries, n_rows)
    n_leaves = len(leaves)
    file_of_leaf = np.array([leaf.file_id for leaf in leaves])
    tokens = np.array([leaf.tokens for leaf in leaves])

    # a leaf scores as its BEST row — the same "a container is a union of topics" rule the live
    # lookup uses; a leaf's mean over its own questions would be measuring dilution, not fit
    leaf_scores = np.full((sims.shape[0], n_leaves), -1.0, dtype=np.float32)
    for leaf_i in range(n_leaves):
        cols = leaf_of_row == leaf_i
        if cols.any():
            leaf_scores[:, leaf_i] = sims[:, cols].max(axis=1)

    order = np.argsort(-leaf_scores, axis=1)
    hits = {k: 0 for k in KS}
    read = 0
    flat = 0.0
    for qi, want in enumerate(truth):
        ranked_files = file_of_leaf[order[qi]]
        for k in KS:
            if want in ranked_files[:k]:
                hits[k] += 1
        read += int(tokens[order[qi][:_TOP_READ]].sum())

        # THE FLOOD, measured the only way this embedder allows: by MARGIN, not by threshold.
        #
        # The obvious metric — "share of leaves whose nearest neighbour in another document sits
        # above cosine 0.90" — is worthless here, and we caught it by checking: on the LIVE library,
        # which routes at 93.3% and has no duplication problem, **95.7% of pages clear that bar**
        # (nearest-other-page cosine: min 0.878, median 0.942). Gemini crowds every similarity into
        # a narrow band, which is exactly what D-028 established and exactly what we forgot.
        #
        # So ask a question that needs no calibration: **is the ranking FLAT?** A flood is not
        # "things are similar" — things are always similar. A flood is the sieve being unable to
        # separate the right document from the restatements behind it. That is score@1 − score@10,
        # and it is scale-free because it is a difference between two numbers from the same run.
        best = leaf_scores[qi][order[qi][0]]
        tenth = leaf_scores[qi][order[qi][min(9, n_leaves - 1)]]
        flat += float(best - tenth)

    n_q = len(truth)
    sizes = np.sort(tokens) if n_leaves else np.array([0])
    return GranularityRow(
        strategy=strategy.name,
        n_leaves=n_leaves,
        median_tokens=int(sizes[len(sizes) // 2]),
        p95_tokens=int(sizes[min(len(sizes) - 1, int(0.95 * len(sizes)))]),
        read_tokens=read // max(n_q, 1),
        margin=flat / max(n_q, 1),
        at_k={k: hits[k] / n_q for k in KS} if n_q else {},
        new_calls=new_calls,
    )
