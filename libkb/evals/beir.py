"""The first externally-valid number this project has ever had (D-039).

Every retrieval figure we have quoted — LOI 56.1%, R@10 90.7%, the cascade A/B — was measured on
questions **our own LLM generated from the very pages it then had to find**. That is a proxy, and
this session alone caught the metric lying four times. A BEIR dataset has human relevance judgments
and real user questions; nobody can argue with the number, including us.

FiQA-2018 is the one that fits the brief: **648 test questions written by actual people** on
StackExchange/Reddit finance ("Why does Charles Schwab have a Mandatory Settlement Period after
selling stocks?"), 57,638 documents, human binary qrels. Its BM25 baseline (nDCG@10 = 0.236) is
published, so we have a bar and not just a number. (NFCorpus was the cheaper candidate and it was
REJECTED after inspection: its 323 test "queries" are keywords — `deafness`, `cumin`,
`Czechoslovakia` — median 2 words. It measures a machine we are not building.)

**Why this file exists is an economic argument, not just a scientific one.** Indexing 57,638
documents through the question flywheel means 57,638 generation calls — ~86M tokens, for a corpus
that is merely medium-sized. Embedding the text costs ~11M *embedding* tokens and **zero
generation**. The flywheel is not a design choice we can afford at scale; it is the ceiling on how
large the library can ever get. So this harness indexes TEXT, and measures whether that survives.

VECTORS ARE CACHED TO DISK. The embeddings are the expensive artifact; scoring them is free. Change
the metric, change the pooling, add a reranker — re-score for nothing. That is D-035, applied before
the money is spent rather than after.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import structlog

from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)

KS = (1, 3, 10, 100)
_MAX_DOC_CHARS = 8000
_EMBED_CHUNK = 500  # progress granularity; the client batches internally


@dataclass
class Dataset:
    name: str
    doc_ids: list[str]
    doc_texts: list[str]
    queries: dict[str, str]  # qid → question
    qrels: dict[str, dict[str, int]]  # qid → {doc_id: graded relevance}

    @property
    def chars(self) -> int:
        return sum(len(t) for t in self.doc_texts)

    @property
    def embed_tokens(self) -> int:
        return self.chars // 4  # same 4-chars-per-token estimate used everywhere else


def load(root: Path | str, split: str = "test") -> Dataset:
    """Read a BEIR dataset directory (corpus.jsonl, queries.jsonl, qrels/<split>.tsv)."""
    root = Path(root)
    doc_ids: list[str] = []
    doc_texts: list[str] = []
    for line in (root / "corpus.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        title = (row.get("title") or "").strip()
        text = (row.get("text") or "").strip()
        doc_ids.append(row["_id"])
        # title first: it is the document's own claim about what it is, and truncation must never
        # take it away
        doc_texts.append((f"{title}\n\n{text}" if title else text)[:_MAX_DOC_CHARS])

    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    with (root / "qrels" / f"{split}.tsv").open(encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        next(reader, None)  # header
        for qid, did, score in reader:
            qrels[qid][did] = int(score)

    queries: dict[str, str] = {}
    for line in (root / "queries.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        if row["_id"] in qrels:  # only the split's queries
            queries[row["_id"]] = row["text"]

    return Dataset(root.name, doc_ids, doc_texts, queries, dict(qrels))


def embed_corpus(
    data: Dataset, cache: Path, *, llm: LLM | None = None, progress=None
) -> np.ndarray:
    """Embed once, keep forever. The vectors are the expensive artifact (D-035)."""
    if cache.exists():
        vectors = np.load(cache)
        if len(vectors) == len(data.doc_ids):
            if progress:
                progress(f"cached: {len(vectors):,} document vectors — nothing to spend")
            return vectors
        if progress:
            progress(f"cache is stale ({len(vectors):,} ≠ {len(data.doc_ids):,}) — re-embedding")

    llm = llm or get_llm()
    cache.parent.mkdir(parents=True, exist_ok=True)
    chunks: list[np.ndarray] = []
    for i in range(0, len(data.doc_texts), _EMBED_CHUNK):
        batch = data.doc_texts[i : i + _EMBED_CHUNK]
        chunks.append(llm.embed(batch))  # RETRIEVAL_DOCUMENT — the task type's actual purpose
        if progress:
            done = min(i + _EMBED_CHUNK, len(data.doc_texts))
            progress(f"embedded {done:,}/{len(data.doc_texts):,} documents")
    vectors = np.vstack(chunks)
    np.save(cache, vectors)
    return vectors


@dataclass
class BenchRow:
    metric: str
    at_k: dict[int, float] = field(default_factory=dict)


def score(
    data: Dataset, doc_vecs: np.ndarray, query_vecs: np.ndarray, qids: list[str]
) -> list[BenchRow]:
    """nDCG@10 (BEIR's metric, so the number is comparable) plus Recall@k (ours, so it is
    interpretable: the cascade's whole design rests on the answer being INSIDE the shortlist)."""
    rankings = []
    for qi in range(len(qids)):
        order = np.argsort(-(doc_vecs @ query_vecs[qi]))[: max(KS)]
        rankings.append([int(i) for i in order])
    return score_rankings(data, rankings, qids)


def score_rankings(data: Dataset, rankings: list[list[int]], qids: list[str]) -> list[BenchRow]:
    """The SAME metric, applied to ranked document INDICES from any retriever — dense, BM25, or a
    fusion of them.

    Split out for one reason: this project has been misled by its own measurement seven times
    (SCORECARD §6), and the cheapest guard against an eighth is that competing arms cannot be scored
    by subtly different code. One nDCG, one Recall, one definition of "counted"."""
    index_of = {doc_id: i for i, doc_id in enumerate(data.doc_ids)}
    ndcg = {k: 0.0 for k in KS}
    recall = {k: 0.0 for k in KS}
    counted = 0

    for qi, qid in enumerate(qids):
        gold = {d: g for d, g in data.qrels[qid].items() if g > 0 and d in index_of}
        if not gold:
            continue
        counted += 1
        ranked = [data.doc_ids[i] for i in rankings[qi][: max(KS)]]

        for k in KS:
            top = ranked[:k]
            dcg = sum(
                gold.get(d, 0) / np.log2(rank + 2) for rank, d in enumerate(top)
            )  # binary/graded gains, log2 discount
            ideal = sorted(gold.values(), reverse=True)[:k]
            idcg = sum(g / np.log2(rank + 2) for rank, g in enumerate(ideal))
            ndcg[k] += (dcg / idcg) if idcg else 0.0
            recall[k] += len(set(top) & set(gold)) / len(gold)

    n = max(counted, 1)
    return [
        BenchRow("nDCG", {k: ndcg[k] / n for k in KS}),
        BenchRow("Recall", {k: recall[k] / n for k in KS}),
    ]


def run(
    data: Dataset, cache: Path, *, llm: LLM | None = None, progress=None
) -> tuple[list[BenchRow], int]:
    llm = llm or get_llm()
    doc_vecs = embed_corpus(data, cache, llm=llm, progress=progress)
    qids = sorted(data.queries)
    if progress:
        progress(f"embedding {len(qids)} real user questions")
    query_vecs = llm.embed([data.queries[q] for q in qids], task="RETRIEVAL_QUERY")
    return score(data, doc_vecs, query_vecs, qids), len(qids)
