"""Routing-eval tests (P3) — all LLM-free: cases come from a hand-built catalog, scoring runs
against synthetic NavResults."""

import numpy as np
import pytest

from libkb import seed
from libkb.agent.navigator import NavResult
from libkb.agent.tools import NavEvent
from libkb.catalog.store import Catalog
from libkb.config import get_settings
from libkb.evals.dataset import EvalCase, build_cases
from libkb.evals.gates import EvalGates, check_gates
from libkb.evals.runner import CaseResult, aggregate, score_case
from libkb.exceptions import LLMError
from libkb.library.models import PageContent
from libkb.library.store import LibraryStore


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store(tmp_path):
    s = LibraryStore(tmp_path / "library")
    s.init_library()
    seed.apply(s)
    return s


def _catalog(tmp_path, rows):
    cat = Catalog(tmp_path / "catalog.db")
    vec = np.ones((1, 3), dtype=np.float32)
    for r in rows:
        cat.add_page(
            page_id=r["page_id"],
            book_id=r["book_id"],
            path=r["path"],
            texts=[r["text"]],
            langs=[r["lang"]],
            embeddings=vec,
        )
    return cat


# ---------------------------------------------------------------- dataset


def test_build_cases_one_per_page_limit_and_domain(tmp_path):
    def row(pid, path, text, lang, book="b1"):
        return {"page_id": pid, "book_id": book, "path": path, "text": text, "lang": lang}

    rows = [
        row("p1", "AI ▸ RAG ▸ Book ▸ P1", "q1a", "en"),
        row("p1", "AI ▸ RAG ▸ Book ▸ P1", "q1b", "vi"),
        row("p2", "AI ▸ RAG ▸ Book ▸ P2", "q2", "en"),
        row("p3", "Retail ▸ KPI ▸ Book ▸ P3", "q3", "en", book="b2"),
    ]
    cat = _catalog(tmp_path, rows)

    cases = build_cases(cat, limit=10, seed=1)
    assert len(cases) == 3  # one per page, p1 deduped
    assert len({c.target_page_id for c in cases}) == 3

    ai = build_cases(cat, domain="AI", seed=1)
    assert {c.target_page_id for c in ai} == {"p1", "p2"}
    assert all(c.target_path.startswith("AI") for c in ai)

    assert len(build_cases(cat, limit=2, seed=1)) == 2


# ---------------------------------------------------------------- scoring


def _target(store):
    book_id = store.resolve_path("ai/rag/advanced-rag-techniques")
    page = next(c for c in store.children(book_id) if c.kind == "page")
    refs = {r.kind: r.id for r in store.path_of(page.id)}
    return page.id, book_id, refs


def _case(page_id):
    return EvalCase("q", "en", target_page_id=page_id, target_book_id="b", target_path="p")


def test_score_reaches_page_via_pages(store):
    page_id, book_id, _ = _target(store)
    nav = NavResult(
        status="FOUND",
        pages=[PageContent(page_id=page_id, book_id=book_id, title="t", markdown="m")],
        hops=4,
    )
    res = score_case(store, _case(page_id), nav)
    assert res.level == "page"
    assert res.reached_page


def test_score_reaches_book_only(store):
    page_id, book_id, _ = _target(store)
    nav = NavResult(
        status="NOT_FOUND",
        events=[NavEvent("open", "Advanced RAG Techniques", "book", book_id)],
        hops=3,
    )
    res = score_case(store, _case(page_id), nav)
    assert res.level == "book"
    assert not res.reached_page


def test_score_reaches_domain_only(store):
    page_id, _, refs = _target(store)
    nav = NavResult(status="NOT_FOUND", events=[NavEvent("enter", "AI", "domain", refs["domain"])])
    res = score_case(store, _case(page_id), nav)
    assert res.level == "domain"


def test_score_miss(store):
    page_id, _, _ = _target(store)
    # a node sharing NO ancestor with the target (Uncatalogued hangs off the root)
    from libkb.library.models import UNCATALOGUED_ID

    nav = NavResult(
        status="NOT_FOUND",
        events=[NavEvent("enter", "Uncatalogued", "shelf", UNCATALOGUED_ID)],
    )
    res = score_case(store, _case(page_id), nav)
    assert res.level == "miss"


def test_score_survives_a_target_page_that_no_longer_exists(store):
    """A held-out set is frozen; a book re-ingested afterwards gets fresh ULIDs (the PDF book,
    D-045), so a target_page_id can point at a page that is gone. Scoring must count that a miss,
    not crash the whole run — one stale case cost a paid 30-query eval its results before this."""
    page_id, book_id, _ = _target(store)
    nav = NavResult(
        status="FOUND",
        pages=[PageContent(page_id=page_id, book_id=book_id, title="t", markdown="m")],
    )
    res = score_case(store, _case("nd_this_id_is_not_in_the_library"), nav)
    assert res.level == "miss"


def test_score_credits_ancestors_of_what_was_touched(store):
    """Reaching a node means reaching its ancestors — entering a sibling shelf under AI still
    means the walk got the DOMAIN right (it had to pass through AI to get there)."""
    page_id, _, _ = _target(store)  # target lives under AI ▸ RAG
    sibling_shelf = store.resolve_path("ai/llm")
    nav = NavResult(status="NOT_FOUND", events=[NavEvent("enter", "LLM", "shelf", sibling_shelf)])
    assert score_case(store, _case(page_id), nav).level == "domain"


def test_shortcut_wrong_page_right_book_scores_book_not_miss(store):
    """The shortcut jumps straight to a page; its events carry no node_id. Without crediting the
    page's ancestors, a wrong page in the RIGHT book used to score `miss` (D-029 §4.1)."""
    page_id, book_id, _ = _target(store)
    other_page = next(c for c in store.children(book_id) if c.kind == "page" and c.id != page_id)
    nav = NavResult(
        status="FOUND",
        pages=[store.page(other_page.id)],
        events=[NavEvent("lookup", "card catalog", None, None)],  # node_id is None in production
    )
    assert score_case(store, _case(page_id), nav).level == "book"


# ---------------------------------------------------------------- aggregate + gates


def _cr(level, *, answer_ok=False, tokens=0):
    status = "NOT_FOUND" if level == "miss" else "FOUND"
    return CaseResult(
        case=_case("p"),
        status=status,
        level=level,
        hops=3,
        backtracks=1,
        answer_ok=answer_ok,
        input_tokens=tokens,
    )


def test_aggregate_is_monotone():
    report = aggregate([_cr("page"), _cr("book"), _cr("shelf"), _cr("miss")], mode="walk")
    assert report.n == 4
    assert report.page_acc == 0.25
    assert report.book_acc == 0.5  # page + book
    assert report.shelf_acc == 0.75  # page + book + shelf
    assert report.domain_acc == 0.75  # everything but the miss
    assert report.found_rate == 0.75
    assert report.avg_hops == 3.0


def test_aggregate_empty():
    report = aggregate([], mode="walk")
    assert report.n == 0
    assert report.page_acc == 0.0
    assert report.answer_acc == 0.0


def test_answer_acc_is_independent_of_page_acc():
    """The whole point of the judge (§3.0): a walk can land on a DIFFERENT page and still answer
    the question perfectly. page_acc calls that a miss; answer_acc — the metric that decides —
    calls it a win."""
    report = aggregate(
        [
            _cr("book", answer_ok=True, tokens=1000),  # wrong page, right answer
            _cr("page", answer_ok=False, tokens=3000),  # right page, bad answer
        ],
        mode="walk",
    )
    assert report.page_acc == 0.5
    assert report.answer_acc == 0.5  # …and they disagree on WHICH case succeeded
    assert report.results[0].answer_ok and not report.results[0].reached_page
    assert report.mean_input_tokens == 2000  # the cost side of the union-TOC bet (§2.4)


def test_the_only_armed_gate_is_the_answer():
    """`answer_acc` is armed from the A/B (D-031: shelf 96.7% − 1.6 se → 0.90). `page_acc` must stay
    UNARMED: it scores a walk a miss when it answers perfectly from a sibling page, so gating it
    would punish the system for being right."""
    gates = EvalGates()
    assert gates.armed
    assert gates.min_answer_acc == 0.90
    assert gates.min_page_acc is None and gates.min_book_acc is None

    # a walk that reaches the wrong page every time but ANSWERS every time still passes…
    all_wrong_page = aggregate([_cr("book", answer_ok=True) for _ in range(10)], mode="walk")
    assert all_wrong_page.page_acc == 0.0
    assert check_gates(all_wrong_page)[0]

    # …and a real regression in answers trips it
    regressed = aggregate(
        [_cr("page", answer_ok=True)] * 8 + [_cr("page", answer_ok=False)] * 2, mode="walk"
    )
    passed, failures = check_gates(regressed)  # answer_acc 0.80 < 0.90
    assert not passed and "answer_acc" in failures[0]


def test_gates_pass_and_fail_once_armed():
    report = aggregate(
        [_cr("page", answer_ok=True), _cr("book"), _cr("miss"), _cr("miss")], mode="walk"
    )
    # answer_acc = 0.25, page_acc = 0.25, book_acc = 0.50
    passed, failures = check_gates(
        report, EvalGates(min_answer_acc=0.9, min_page_acc=0.9, min_book_acc=0.9)
    )
    assert not passed and len(failures) == 3

    ok, none = check_gates(report, EvalGates(min_answer_acc=0.0))
    assert ok and none == []


# ---------------------------------------------------------------- the judge


class FakeJudgeLLM:
    """Scripted judge: returns whatever verdict the test asked for, and records the prompt."""

    def __init__(self, correct=True, reason="ok"):
        self._data = {"correct": correct, "reason": reason}
        self.prompts = []
        self.models = []

    def load_prompt(self, name, **kw):
        self.prompt_name = name
        return "|".join(f"{k}={v}" for k, v in kw.items())

    def generate_json(self, contents, *, schema, model=None, **kw):
        self.prompts.append(contents)
        self.models.append(model)
        return self._data


def test_judge_grades_the_answer_and_runs_on_the_lite_tier():
    from libkb.evals.judge import judge_answer

    llm = FakeJudgeLLM(correct=True, reason="covers the formula")
    verdict = judge_answer("what is GMROI?", "GMROI = margin / avg inventory cost.", "ref", llm=llm)

    assert verdict.correct and verdict.reason == "covers the formula"
    assert llm.prompt_name == "judge_answer"
    assert llm.models == [get_settings().model_lite]  # D-027: judging is bulk, cheap work


def test_judge_scores_an_empty_answer_wrong_without_calling_the_model():
    from libkb.evals.judge import judge_answer

    llm = FakeJudgeLLM()
    assert not judge_answer("q", "   ", "ref", llm=llm).correct
    assert llm.prompts == []  # free


def test_judge_survives_a_model_failure(monkeypatch):
    from libkb.evals import judge as judge_mod

    class Boom(FakeJudgeLLM):
        def generate_json(self, *a, **kw):
            raise LLMError("quota exhausted")

    verdict = judge_mod.judge_answer("q", "an answer", "ref", llm=Boom())
    assert not verdict.correct  # a failed judge must not abort a 30-case run mid-way
    assert "judge failed" in verdict.reason


# ---------------------------------------------------------------- held-out paraphrase set


class FakeParaphraseLLM(FakeJudgeLLM):
    def __init__(self, question="làm sao tính vòng quay hàng tồn?"):
        super().__init__()
        self._data = {"question": question}


def test_paraphrase_keeps_the_target_and_replaces_only_the_question():
    from libkb.evals.holdout import paraphrase_cases

    case = EvalCase("Define inventory turnover ratio", "vi", "pg1", "bk1", "Retail ▸ KPI ▸ P")
    [fresh] = paraphrase_cases([case], llm=FakeParaphraseLLM())

    assert fresh.question == "làm sao tính vòng quay hàng tồn?"
    assert (fresh.target_page_id, fresh.target_book_id, fresh.lang) == ("pg1", "bk1", "vi")


def test_paraphrase_falls_back_to_the_original_on_failure():
    from libkb.evals.holdout import paraphrase_cases

    class Boom(FakeParaphraseLLM):
        def generate_json(self, *a, **kw):
            raise LLMError("quota exhausted")

    case = EvalCase("original", "en", "pg1", "bk1", "p")
    # a half-built holdout set is worse than a slightly leaky one — keep the case, keep going
    assert paraphrase_cases([case], llm=Boom())[0].question == "original"


def test_holdout_round_trips_through_disk(tmp_path):
    from libkb.evals.holdout import load_cases, save_cases

    cases = [EvalCase("q1", "vi", "pg1", "bk1", "p1"), EvalCase("q2", "en", "pg2", "bk2", "p2")]
    path = tmp_path / "nested" / "holdout.json"
    save_cases(path, cases)

    # both A/B arms must be scored on byte-identical questions, so the set is written once and read
    assert load_cases(path) == cases
