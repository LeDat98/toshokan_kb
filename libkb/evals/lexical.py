"""BM25, and the question D-032 answered too broadly.

**What D-032 actually measured.** Fusing BM25 into retrieval lost on both query distributions we had
— generated questions (LOI page R@10 90.7% → 78.6%) and held-out colloquial Vietnamese paraphrases
(R@1 83.3% → 43.3%) — at every fusion weight, monotonically. That is a real result and it is not in
dispute. What IS in dispute is how widely it was then read, because both of those test sets are
adversarial to BM25 by construction:

  * the generated questions were written BY an LLM FROM the very pages being searched (the
    tautology SCORECARD calls metric bug 6.4), and
  * the paraphrase set is **cross-lingual** — Vietnamese questions against English pages. BM25
    matches TOKENS. Two languages share almost none. Testing BM25 there is close to testing it
    where it cannot work by definition.

The mechanism BM25 exists for — a rare term or identifier appearing VERBATIM in the question
("GMROI", "HNSW", a SKU code, an article number) — was in neither set. `tests/test_hybrid.py` shows
that mechanism working. So the honest state is: **untested where it lives.**

**And a second, independent suspect: our configuration.** `catalog/store.py::_fts_terms` ORs every
word of the question together and filters nothing but 1-character tokens. BM25 sums a contribution
per matched term, so a document matching six common words can outrank the one document matching the
single rare word — IDF discounts the common words, it does not eliminate them. That is *exactly* the
"BM25 latches onto the common ones and drags noise up" behaviour D-032 observed, and it is a
config bug, not a property of BM25. Note the asymmetry it exposes: `library/sections.py` carries a
vi+en stopword list for its snippet scorer, and the lexical path does not use it.

This module exists to separate those three hypotheses with a measurement, on FiQA — 57,638 English
documents, 648 questions real people wrote, human qrels, document vectors already cached. Same
language, real lexical overlap, $0 in generation. The regime where BM25 must win if it ever wins.

**Two correctness checks are built into the run itself**, because this project has been fooled by
its own metrics seven times:
  * the `dense` arm must reproduce SCORECARD §2.2 (nDCG@10 0.621 / R@10 0.701 / R@100 0.920);
  * the `bm25` arm must land near BEIR's **published** FiQA BM25 bar, nDCG@10 = **0.236**.
If either is far off, the harness is wrong and no conclusion may be drawn from it.

The BM25 here is deliberately the one SQLite FTS5 would run — k1=1.2, b=0.75, `unicode61` tokenizing
with `remove_diacritics 2` — so a number measured here is a claim about what production would do,
not about a different retriever that happens to share a name.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import structlog

from libkb.library.sections import _STOP

log = structlog.get_logger(__name__)

# SQLite FTS5's bm25() defaults. Not tuned — matching production is the point.
K1 = 1.2
B = 0.75
# The same constant `catalog/search.py` fuses with. Large enough that rank 1 does not dominate.
RRF_K = 60

_WORD = re.compile(r"[^\w]+", re.UNICODE)
# `remove_diacritics 2` strips combining marks, but Vietnamese `đ` is a distinct codepoint with no
# decomposition — it must be mapped explicitly or "đầu tư" and "dau tu" stay different tokens.
_FOLD = str.maketrans({"đ": "d", "Đ": "d", "ß": "ss"})


def fold(text: str) -> str:
    """Lowercase and strip diacritics, the way `unicode61 remove_diacritics 2` does."""
    lowered = text.lower().translate(_FOLD)
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tokenize(text: str) -> list[str]:
    """Tokens, FTS5-style: fold, split on non-word, drop 1-character tokens.

    NO STEMMING — `unicode61` has none, so "running" and "run" are different tokens here exactly as
    they are in the live index. Do not quietly add a stemmer: it would make this harness measure a
    retriever the production system does not have."""
    return [t for t in _WORD.split(fold(text)) if len(t) > 1]


def query_terms(query: str, *, drop_stopwords: bool) -> list[str]:
    """The query's terms, deduplicated (a word repeated in the question is still one condition).

    `drop_stopwords` is the A/B this module was written for. Production ORs every word and filters
    none — so a long colloquial question contributes a dozen near-empty terms, and a document can
    win on their SUM. The stopword list is the vi+en one `sections.py` already uses for snippets;
    reusing it rather than writing a second one keeps a single source of truth for "which words
    carry no topical signal"."""
    seen: dict[str, None] = {}
    for token in tokenize(query):
        if drop_stopwords and token in _STOP:
            continue
        seen.setdefault(token, None)
    return list(seen)


@dataclass
class BM25:
    """An in-memory BM25 index. Built for measurement, but deliberately the same scoring function
    the catalog's FTS5 would apply, so a result here transfers."""

    postings: dict[str, list[tuple[int, int]]] = field(default_factory=dict)  # term → [(doc, tf)]
    doc_len: np.ndarray = field(default_factory=lambda: np.zeros(0))
    n_docs: int = 0
    avgdl: float = 0.0

    @classmethod
    def build(cls, texts: list[str], *, progress=None) -> BM25:
        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        lengths = np.zeros(len(texts), dtype=np.float32)
        for i, text in enumerate(texts):
            tokens = tokenize(text)
            lengths[i] = len(tokens)
            counts: dict[str, int] = defaultdict(int)
            for token in tokens:
                counts[token] += 1
            for term, tf in counts.items():
                postings[term].append((i, tf))
            if progress and i and i % 10_000 == 0:
                progress(f"indexed {i:,}/{len(texts):,} documents")
        avgdl = float(lengths.mean()) if len(lengths) else 0.0
        return cls(dict(postings), lengths, len(texts), avgdl)

    def df(self, term: str) -> int:
        return len(self.postings.get(term, ()))

    def idf(self, term: str) -> float:
        """Robertson/Sparck-Jones IDF with the +0.5 smoothing FTS5 uses. A term in EVERY document
        scores ~0: that is the mechanism that is supposed to protect us from common words, and the
        measurement below asks whether it is enough on its own."""
        n = self.df(term)
        if n == 0:
            return 0.0
        return math.log(1.0 + (self.n_docs - n + 0.5) / (n + 0.5))

    def rare(self, terms: list[str], *, max_df_ratio: float) -> list[str]:
        """The query terms that are RARE in this corpus — the ones BM25 is actually for.

        This is the trigger `config.py` promised and nobody built: *"the lexical index stays OFF
        until real traffic shows queries where those terms actually appear."* A query with no rare
        term has nothing for BM25 to contribute that the embedder has not already covered, so the
        cheapest correct thing is not to fuse at all."""
        ceiling = max(1, int(self.n_docs * max_df_ratio))
        return [t for t in terms if 0 < self.df(t) <= ceiling]

    def score_docs(self, terms: list[str]) -> np.ndarray:
        """The BM25 score of every document for these terms, OR-ed — the production semantics.

        Three behaviours live in the one expression below, and the middle one is the whole argument
        of this module:
          * `idf(term)` — a rare term counts for more than a common one;
          * **the SUM over terms** — a document matching six common words accumulates six small
            contributions, and can outrank the single document matching the one rare word. IDF
            discounts common words; it does not eliminate them. This is the mechanism behind
            D-032's "BM25 drags noise up", and it is why WHICH terms we send matters as much as
            the scoring function;
          * `tf/(tf + norm)` — occurrences saturate, and long documents are not rewarded for length.
        """
        scores = np.zeros(self.n_docs, dtype=np.float32)
        if not terms or not self.n_docs:
            return scores
        norm = K1 * (1 - B + B * self.doc_len / (self.avgdl or 1.0))
        for term in terms:
            posting = self.postings.get(term)
            if not posting:
                continue
            weight = self.idf(term)
            docs = np.fromiter((d for d, _ in posting), dtype=np.int64, count=len(posting))
            tfs = np.fromiter((f for _, f in posting), dtype=np.float32, count=len(posting))
            scores[docs] += weight * (tfs * (K1 + 1)) / (tfs + norm[docs])
        return scores

    def search(self, terms: list[str], *, top_k: int) -> list[int]:
        """Document indices, best first. A document scoring 0 never appears — BM25 has no notion of
        'closest', so a query whose terms are absent returns nothing rather than something."""
        if not terms or not self.n_docs:
            return []
        scores = self.score_docs(terms)
        hits = np.flatnonzero(scores)
        if not len(hits):
            return []
        k = min(top_k, len(hits))
        best = hits[np.argpartition(-scores[hits], k - 1)[:k]]
        return [int(i) for i in best[np.argsort(-scores[best])]]


def rrf(rankings: list[list[int]], *, top_k: int, k: int = RRF_K) -> list[int]:
    """Reciprocal-rank fusion — by RANK, never by score.

    The reason is measured, not stylistic: our cosines crowd into 0.87–0.90 (D-028) and BM25 scores
    live on an unrelated scale, so any weighted sum would be calibrating noise. RRF only asks *how
    near the top did each ranker put this?* An empty ranking contributes nothing, so fusion degrades
    cleanly to the other list rather than to garbage."""
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            scores[doc] += 1.0 / (k + rank)
    return sorted(scores, key=lambda d: -scores[d])[:top_k]


def dense_rankings(doc_vecs: np.ndarray, query_vecs: np.ndarray, *, top_k: int) -> list[list[int]]:
    """Top-k document indices per query, batched. Identical maths to `beir.score`'s per-query
    argsort; batched only because 648 × 57,638 × 3,072 one query at a time is wasteful."""
    out: list[list[int]] = []
    sims = doc_vecs @ query_vecs.T  # (docs, queries)
    for qi in range(sims.shape[1]):
        column = sims[:, qi]
        k = min(top_k, column.shape[0])
        best = np.argpartition(-column, k - 1)[:k]
        out.append([int(i) for i in best[np.argsort(-column[best])]])
    return out


# --------------------------------------------------------------------------- the arms

# arm → (uses dense, uses lexical, drop stopwords, rare-term-gated)
ARMS: dict[str, tuple[bool, bool, bool, bool]] = {
    "dense": (True, False, False, False),
    "bm25": (False, True, False, False),
    "bm25-stop": (False, True, True, False),
    "hybrid": (True, True, False, False),  # ← what `hybrid_shortlist=True` does TODAY
    "hybrid-stop": (True, True, True, False),  # ← is the config the bug?
    "hybrid-rare": (True, True, True, True),  # ← fuse ONLY when the query has a rare term
}
DEFAULT_ARMS = ("dense", "bm25", "hybrid", "hybrid-stop", "hybrid-rare")


@dataclass
class Complement:
    """Does lexical see anything dense is BLIND to? — a different question from "does fusing help".

    Fusion asks the two rankers to vote on one list, so a much weaker voter drags a strong one
    toward the middle no matter how it is weighted. **Complementarity asks whether the weak ranker
    finds gold the strong one never retrieved at all.** Those come apart completely: BM25 can lose
    every fusion arm and still be the only thing that ever finds a ticker symbol or an article
    number.

    This is the number that decides the ARCHITECTURE. If `rescued` is ~0, lexical adds literally
    nothing here and the case closes for good. If it is meaningful, the right shape is not fusion
    but **escalation** — an exact-search TOOL the agent reaches for when it sees an identifier,
    which is how coding agents actually use grep, rather than a score mixed into every query.
    """

    n_queries: int = 0
    gold_total: int = 0
    dense_found: int = 0
    lexical_found: int = 0
    rescued: int = 0  # gold lexical found that dense did NOT — the whole point
    rescued_queries: int = 0  # queries with at least one such document
    dense_blind: int = 0  # queries where dense found NO gold at all
    dense_blind_rescued: int = 0  # ...of those, how many lexical rescued


def complementarity(
    gold_per_query: list[set[int]], dense: list[list[int]], lexical: list[list[int]], *, k: int
) -> Complement:
    """Set arithmetic on the two top-k lists. No ranking, no fusion — just: who found what."""
    out = Complement(n_queries=len(gold_per_query))
    for gold, d_rank, l_rank in zip(gold_per_query, dense, lexical, strict=True):
        if not gold:
            continue
        d_top, l_top = set(d_rank[:k]), set(l_rank[:k])
        d_hit, l_hit = gold & d_top, gold & l_top
        only_lexical = l_hit - d_hit
        out.gold_total += len(gold)
        out.dense_found += len(d_hit)
        out.lexical_found += len(l_hit)
        out.rescued += len(only_lexical)
        out.rescued_queries += 1 if only_lexical else 0
        if not d_hit:
            out.dense_blind += 1
            out.dense_blind_rescued += 1 if l_hit else 0
    return out


@dataclass
class ArmPlan:
    arm: str
    fused: int = 0  # queries where lexical actually contributed (the gate's selectivity)
    lexical_empty: int = 0  # queries where BM25 matched nothing at all


def rank_arm(
    arm: str,
    *,
    index: BM25,
    queries: list[str],
    dense: list[list[int]],
    top_k: int,
    max_df_ratio: float = 0.01,
) -> tuple[list[list[int]], ArmPlan]:
    """One arm's ranked document indices per query, plus what the arm actually did.

    `max_df_ratio=0.01` means "appears in at most 1% of the corpus". On FiQA that is ≤576 of 57,638
    documents — a term like a ticker symbol or a fund name, not "money" or "tax"."""
    use_dense, use_lexical, drop_stop, gate = ARMS[arm]
    plan = ArmPlan(arm)
    out: list[list[int]] = []
    for qi, query in enumerate(queries):
        rankings: list[list[int]] = []
        if use_dense:
            rankings.append(dense[qi])
        if use_lexical:
            terms = query_terms(query, drop_stopwords=drop_stop)
            if gate:
                terms = index.rare(terms, max_df_ratio=max_df_ratio)
            lexical = index.search(terms, top_k=top_k) if terms else []
            if lexical:
                rankings.append(lexical)
                plan.fused += 1
            elif use_dense:
                plan.lexical_empty += 1
        out.append(
            rrf(rankings, top_k=top_k) if len(rankings) > 1 else (rankings[0] if rankings else [])
        )
    return out, plan
