"""Run eval cases through the librarian and score them.

PRIMARY metric: `answer_acc` — an LLM judge over the final answer (see evals/judge.py for why the
old primary was biased against shelf routing).

Secondary DIAGNOSTIC: how deep the routing got. A case scores at the deepest target-ancestor the
walk reached — page ⊃ book ⊃ shelf ⊃ domain ⊃ miss. Buckets are monotone (a page hit is a book hit
too), so `book_acc` reads as "landed in the right book at least". These say *where* a failure
happened; they do not say whether the reader was served.

Also reported: mean input tokens per query — the cost side of the union-TOC bet (§2.4). Judge calls
are deliberately excluded: they are eval scaffolding, not part of the product.

Three modes: `walk` (pure description routing, no catalog at all), `assisted` (walk +
ask_librarian), `shortcut` (the full system incl. the catalog fast path).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field

from libkb.agent.navigator import NavResult
from libkb.agent.orchestrator import QueryResult, answer_query
from libkb.catalog.store import Catalog
from libkb.evals.dataset import EvalCase
from libkb.evals.judge import judge_answer
from libkb.exceptions import NodeNotFound
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

_LEVELS = ("domain", "shelf", "book", "page")


@dataclass
class CaseResult:
    case: EvalCase
    status: str  # FOUND | NOT_FOUND
    level: str  # page | book | shelf | domain | miss
    hops: int
    backtracks: int
    answer_ok: bool = False  # the primary metric, per case
    answer: str = ""
    judge_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def reached_page(self) -> bool:
        return self.level == "page"


@dataclass
class EvalReport:
    n: int
    mode: str
    answer_acc: float
    page_acc: float
    book_acc: float
    shelf_acc: float
    domain_acc: float
    found_rate: float
    avg_hops: float
    avg_backtracks: float
    mean_input_tokens: float = 0.0
    mean_output_tokens: float = 0.0
    judged: bool = True
    results: list[CaseResult] = field(default_factory=list)


def score_case(store: LibraryStore, case: EvalCase, nav: NavResult) -> CaseResult:
    touched = {e.node_id for e in nav.events if e.node_id}
    touched |= {p.page_id for p in nav.pages}
    # Reaching a node means reaching its ancestors. The walk enters them explicitly, but the
    # shortcut jumps straight to a page (its lookup/found events carry no node_id) — without this
    # expansion a shortcut that lands on the wrong page of the RIGHT book scores `miss`, and every
    # level below `page` is systematically understated.
    visited = set(touched)
    for node_id in touched:
        with contextlib.suppress(NodeNotFound):
            visited |= {ref.id for ref in store.path_of(node_id)}
    level = _deepest_reached(store, case.target_page_id, visited)
    return CaseResult(
        case=case, status=nav.status, level=level, hops=nav.hops, backtracks=nav.backtracks
    )


def _deepest_reached(store: LibraryStore, target_page_id: str, visited: set[str]) -> str:
    best = "miss"
    try:
        path = store.path_of(target_page_id)
    except NodeNotFound:
        # The target page is gone — e.g. a book was re-ingested with fresh ULIDs after the held-out
        # set was frozen (the PDF book, D-037/D-045). Routing can't be scored against a page that no
        # longer exists, so count it a miss — but the answer is still generated and still judged, so
        # one stale target does not kill the whole run (the same fail-soft rule ingest already
        # follows). Depresses page_acc, never answer_acc.
        return "miss"
    for ref in path:  # ordered root → page
        if ref.kind == "root":
            continue
        if ref.id in visited:
            best = ref.kind  # deepest visited wins
    return best


def aggregate(results: list[CaseResult], *, mode: str = "", judged: bool = True) -> EvalReport:
    n = len(results)
    if n == 0:
        return EvalReport(0, mode, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, judged=judged)

    def frac(pred: Callable[[CaseResult], bool]) -> float:
        return sum(1 for r in results if pred(r)) / n

    return EvalReport(
        n=n,
        mode=mode,
        answer_acc=frac(lambda r: r.answer_ok),
        page_acc=frac(lambda r: r.level == "page"),
        book_acc=frac(lambda r: r.level in ("page", "book")),
        shelf_acc=frac(lambda r: r.level in ("page", "book", "shelf")),
        domain_acc=frac(lambda r: r.level != "miss"),
        found_rate=frac(lambda r: r.status == "FOUND"),
        avg_hops=sum(r.hops for r in results) / n,
        avg_backtracks=sum(r.backtracks for r in results) / n,
        mean_input_tokens=sum(r.input_tokens for r in results) / n,
        mean_output_tokens=sum(r.output_tokens for r in results) / n,
        judged=judged,
        results=results,
    )


ProgressCB = Callable[[int, int, CaseResult], None]


def run_eval(
    store: LibraryStore,
    cases: list[EvalCase],
    *,
    mode: str = "walk",
    catalog: Catalog | None = None,
    llm: LLM | None = None,
    judge: bool = True,
    progress: ProgressCB | None = None,
) -> EvalReport:
    llm = llm or get_llm()
    results: list[CaseResult] = []
    for i, case in enumerate(cases, 1):
        before_in = getattr(llm, "total_input_tokens", 0)
        before_out = getattr(llm, "total_output_tokens", 0)

        query = _run_one(store, case, mode, catalog, llm)

        # snapshot the query's cost BEFORE judging, so judge tokens never enter the product's bill
        res = score_case(store, case, query.nav)
        res.input_tokens = getattr(llm, "total_input_tokens", 0) - before_in
        res.output_tokens = getattr(llm, "total_output_tokens", 0) - before_out
        res.answer = query.answer.text

        if judge:
            verdict = _judge(store, case, query, llm)
            res.answer_ok, res.judge_reason = verdict
        results.append(res)
        if progress:
            progress(i, len(cases), res)
    return aggregate(results, mode=mode, judged=judge)


def _judge(store: LibraryStore, case: EvalCase, query: QueryResult, llm: LLM) -> tuple[bool, str]:
    if query.answer.status != "answered":
        return False, "not_found"  # an honest refusal is still a failure to serve — and it is free
    try:
        reference = store.page(case.target_page_id).markdown
    except NodeNotFound:
        return False, "target page missing from the library"
    verdict = judge_answer(case.question, query.answer.text, reference, llm=llm)
    return verdict.correct, verdict.reason


def _run_one(
    store: LibraryStore, case: EvalCase, mode: str, catalog: Catalog | None, llm: LLM | None
) -> QueryResult:
    """Every mode goes through the real product entry point, so the answer being judged is the
    answer a reader would have received."""
    if mode == "shortcut":
        return answer_query(case.question, store=store, catalog=catalog, llm=llm)
    if mode in ("assisted", "cascade"):
        # cascade NEEDS the index — the embedder is the sieve. But no shortcut: the librarian must
        # still triage and answer, so what we measure is the architecture, not a lookup table.
        return answer_query(case.question, store=store, catalog=catalog, llm=llm, shortcut=False)
    # walk: no catalog at all — not as a shortcut, not as ask_librarian
    return answer_query(case.question, store=store, llm=llm, shortcut=False, use_catalog=False)
