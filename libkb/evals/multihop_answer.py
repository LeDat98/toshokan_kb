"""Does the cascade ANSWER a multi-hop question — and does it stay honest when it cannot? (D-042)

`bench-multihop` measured the SIEVE and found something the whole session had been guessing at:

    AllGold@20  93.5%   ← the evidence IS there; the sieve found it
    AllGold@3   29.6%   ← the cascade opens 3 pages, so this is what the answerer ever sees

The sieve is not the bottleneck. **The basket is.** But a retrieval ceiling is not an answer: more
evidence can also drown an answerer (the "lost in the middle" failure), so a bigger basket has to be
MEASURED, not assumed. That is arm A vs arm B here.

And the second thing, which matters more than accuracy: **301 `null_query` rows** — questions whose
answer is literally "Insufficient information." No page in the library answers them. They are the
first real test of the rule this project calls non-negotiable (P6):

    no evidence ⇒ an honest NOT_FOUND, never an improvisation

An eval that only scores answerable questions rewards a system for guessing. This one punishes it.
Two numbers, and they pull in opposite directions:

    honesty   of the null queries, how many did we correctly refuse?
    coward    of the ANSWERABLE queries, how many did we wrongly refuse?

A librarian who says "not found" to everything scores 100% honesty and is useless. Report both.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from libkb.agent.orchestrator import answer_query_safe
from libkb.catalog.store import Catalog
from libkb.concurrency import parallel_map
from libkb.config import get_settings
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)

_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"correct": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["correct"],
}

NULL = "null_query"


@dataclass
class Case:
    query: str
    kind: str
    answer: str  # "Insufficient information." for null_query


@dataclass
class Outcome:
    case: Case
    said_not_found: bool
    correct: bool
    text: str
    pages: int
    input_tokens: int
    output_tokens: int
    # the answerer's OWN confidence (D-046). Captured so the confidence gate can be swept OFFLINE:
    # run once with the gate OFF (cascade_min_confidence=low) and every floor becomes a free
    # re-scoring of these rows, instead of one paid run per threshold.
    confidence: str = "medium"


@dataclass
class Report:
    n: int = 0
    errors: int = 0  # transport failures — reported, never scored (they are evidence of nothing)
    by_kind: dict[str, list[Outcome]] = field(default_factory=dict)
    # batch-level token totals from the client counter delta. Under a concurrent pool the per-case
    # deltas interleave and are meaningless, so the whole-run figure is the honest one to price by.
    input_total: int = 0
    output_total: int = 0

    def add(self, outcome: Outcome) -> None:
        self.n += 1
        self.by_kind.setdefault(outcome.case.kind, []).append(outcome)

    @property
    def answerable(self) -> list[Outcome]:
        return [o for k, v in self.by_kind.items() if k != NULL for o in v]

    @property
    def nulls(self) -> list[Outcome]:
        return self.by_kind.get(NULL, [])


def load_cases(
    path: Path | str, *, limit: int | None, seed: int = 11, null_only: bool = False
) -> list[Case]:
    """Sample STRATIFIED by question type, so a 200-case run still contains the null queries and
    the inference queries — the two hardest things in the set — in their real proportion.

    `null_only` runs every unanswerable question and nothing else. That is not a niche mode: a
    200-case stratified sample carries only ~24 nulls, and the basket-3 vs basket-10 honesty gap
    (91.7% vs 83.3%) was **two cases**. The single property this project calls non-negotiable — no
    evidence ⇒ an honest NOT_FOUND — cannot be left resting on a difference of two.
    """
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = [Case(r["query"], r["question_type"], str(r["answer"])) for r in rows]
    if null_only:
        return [c for c in cases if c.kind == NULL]
    if not limit or limit >= len(cases):
        return cases
    rng = random.Random(seed)
    by_kind: dict[str, list[Case]] = {}
    for case in cases:
        by_kind.setdefault(case.kind, []).append(case)
    out: list[Case] = []
    for kind, group in sorted(by_kind.items()):
        share = max(1, round(limit * len(group) / len(cases)))
        out += rng.sample(group, min(share, len(group)))
    rng.shuffle(out)
    return out[:limit]


def _judge(case: Case, answer: str, llm: LLM) -> bool:
    settings = get_settings()
    prompt = (
        "You are grading a question-answering system against a reference answer.\n\n"
        f"QUESTION:\n{case.query}\n\n"
        f"REFERENCE ANSWER:\n{case.answer}\n\n"
        f"SYSTEM ANSWER:\n{answer[:3000]}\n\n"
        "Mark it correct if the system answer conveys the reference answer — the same entity, the "
        "same yes/no, the same fact. Extra correct detail is fine. Different wording is fine. Mark "
        "it incorrect if it states a different fact, names a different entity, or does not answer.\n"
        'Return JSON: {"correct": true|false, "reason": "<one clause>"}'
    )
    try:
        data = llm.generate_json(prompt, schema=_JUDGE_SCHEMA, model=settings.model_lite)
        return bool(data.get("correct"))
    except Exception as exc:  # a flaky judge must not kill a run that already cost real tokens
        log.warning("judge_failed", error=str(exc))
        return False


def run(
    cases: list[Case],
    *,
    store: LibraryStore,
    catalog: Catalog,
    llm: LLM | None = None,
    workers: int | None = None,
    progress=None,
) -> Report:
    """Answer every case; parallel by default (backlog #1). Each case is independent — the pool
    shares one LLM client and one read-only catalog. `workers <= 1` is the old sequential loop."""
    llm = llm or get_llm()
    workers = get_settings().eval_concurrency if workers is None else workers
    concurrent = workers > 1 and len(cases) > 1
    if catalog.count():  # build the vector matrix ONCE, before threads race to load it lazily
        catalog.vectors()
    report = Report()
    before = (llm.total_input_tokens, llm.total_output_tokens)

    def one(case: Case) -> Outcome | None:
        # per-case token deltas are only meaningful when calls do not interleave; under the pool we
        # price the whole batch (report.input_total, below) and leave per-case at 0.
        t0 = (llm.total_input_tokens, llm.total_output_tokens)
        try:
            result = answer_query_safe(case.query, store=store, catalog=catalog, llm=llm)
        except Exception as exc:
            # `answer_query_safe` catches LLMError. It does NOT catch a dropped socket, and one of
            # those killed a 301-case run after ~200 paid queries. The answers are the expensive
            # artifact (D-035); a single flaky case costs one case, never the whole run — and it is
            # EXCLUDED from the rates (returned as None), not scored as a miss, because a transport
            # error is evidence for nothing.
            log.warning("case_failed", query=case.query[:60], error=str(exc)[:120])
            return None
        answer = result.answer
        said_not_found = answer.status == "not_found"
        if case.kind == NULL:
            # The ONLY correct behaviour on a question the library cannot answer is to say so.
            correct = said_not_found
        else:
            correct = (not said_not_found) and _judge(case, answer.text, llm)
        return Outcome(
            case=case,
            said_not_found=said_not_found,
            correct=correct,
            text=answer.text,
            pages=len(result.nav.pages),
            input_tokens=0 if concurrent else llm.total_input_tokens - t0[0],
            output_tokens=0 if concurrent else llm.total_output_tokens - t0[1],
            confidence=answer.confidence,
        )

    def note(done: int, total: int) -> None:
        if progress and done % 5 == 0:
            progress(f"{done}/{total}")

    for outcome in parallel_map(one, cases, workers=workers, progress=note):
        if outcome is None:
            report.errors += 1
        else:
            report.add(outcome)
    report.input_total = llm.total_input_tokens - before[0]
    report.output_total = llm.total_output_tokens - before[1]
    return report
