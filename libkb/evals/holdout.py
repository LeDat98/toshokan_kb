"""A held-out paraphrase eval set (ROUTING_REDESIGN §3.1).

The default eval set is **leaked**. Its questions ARE the catalog rows the system embeds and
indexes, so a catalog hit is a lookup of the answer key. Even for the pure `walk` arm the leak is
real, just softer: the questions carry the target page's own vocabulary, which is exactly the
signal the descriptions were built from.

This restates each question the way a reader who has *not* read the page would ask it — vaguer,
plainer, sometimes with the wrong term — while keeping the target page fixed. Expect the baseline
to drop. **That lower number is the real one.**

Generated once with `model_lite` and SAVED to disk, because both arms of an A/B must be scored on
byte-identical questions; regenerating per arm would confound the routing change with question
noise.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from libkb.config import get_settings
from libkb.evals.dataset import EvalCase
from libkb.exceptions import LLMError
from libkb.llm.client import LLM, get_llm

PARAPHRASE_SCHEMA = {
    "type": "object",
    "properties": {"question": {"type": "string"}},
    "required": ["question"],
}

ProgressCB = Callable[[int, int, EvalCase, EvalCase], None]


def paraphrase_case(case: EvalCase, *, llm: LLM | None = None) -> EvalCase:
    """One case → the same case asked colloquially. On failure the original is kept (and the run
    goes on), because a half-built holdout set is worse than a slightly leaky one."""
    llm = llm or get_llm()
    prompt = llm.load_prompt("paraphrase_question", question=case.question, lang=case.lang)
    try:
        data = llm.generate_json(
            prompt,
            schema=PARAPHRASE_SCHEMA,
            model=get_settings().model_lite,
            temperature=0.7,  # variety is the point; a bland restatement is another leak
        )
    except LLMError:
        return case
    text = str(data.get("question", "")).strip()
    if not text:
        return case
    return EvalCase(
        question=text,
        lang=case.lang,
        target_page_id=case.target_page_id,
        target_book_id=case.target_book_id,
        target_path=case.target_path,
    )


def paraphrase_cases(
    cases: list[EvalCase], *, llm: LLM | None = None, progress: ProgressCB | None = None
) -> list[EvalCase]:
    llm = llm or get_llm()
    out: list[EvalCase] = []
    for i, case in enumerate(cases, 1):
        fresh = paraphrase_case(case, llm=llm)
        out.append(fresh)
        if progress:
            progress(i, len(cases), case, fresh)
    return out


def save_cases(path: Path, cases: list[EvalCase]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"n": len(cases), "cases": [asdict(c) for c in cases]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_answers(path: Path, mode: str, results: list) -> None:
    """Persist every answer the eval produced, so it can be RE-JUDGED for free.

    Three times now the metric, not the system, has been the thing that was wrong: `page_acc` was
    biased against shelf routing (D-030); the judge penalised a *richer* answer for drawing on a
    second page (D-035). Each time, finding out cost a full re-run of the arm — walks included.
    It never should again: the answers are the expensive artifact, and grading them is nearly free.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": mode,
        "n": len(results),
        "results": [
            {
                "question": r.case.question,
                "target_page_id": r.case.target_page_id,
                "target_path": r.case.target_path,
                "answer": r.answer,
                "status": r.status,
                "level": r.level,
                "answer_ok": r.answer_ok,
                "judge_reason": r.judge_reason,
                "input_tokens": r.input_tokens,
            }
            for r in results
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cases(path: Path) -> list[EvalCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [EvalCase(**row) for row in data["cases"]]
