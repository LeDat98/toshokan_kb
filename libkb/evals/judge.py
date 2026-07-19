"""LLM-as-judge over the FINAL ANSWER — the eval's primary metric (ROUTING_REDESIGN §3.0).

`page_acc` asks "did the walk reach the exact page that generated the question". That is not a
neutral approximation of "did it work" — it is **biased against shelf routing**. A walk that lays
out 42 pages at once has far more opportunity to land on a *sibling page that answers the question
perfectly*, and `page_acc` scores that a MISS. The very property that makes the union-TOC design
good gets counted as a defect. (Observed live: a question about inventory days was answered
correctly and completely from the *Inventory Turnover* page — scored `miss`.)

So the metric that gates decisions is: **does the final answer actually answer the question**,
graded against the target page's content as the reference. One cheap call on `model_lite` (D-027),
negligible next to a strong-model walk.
"""

from __future__ import annotations

from dataclasses import dataclass

from libkb.config import get_settings
from libkb.exceptions import LLMError
from libkb.llm.client import LLM, get_llm

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "correct": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["correct", "reason"],
}

_MAX_REFERENCE_CHARS = 6000


@dataclass
class Verdict:
    correct: bool
    reason: str


def judge_answer(question: str, answer: str, reference: str, *, llm: LLM | None = None) -> Verdict:
    """Grade one answer against the reference page. Never raises — a judge failure must not abort
    an eval run mid-way; it scores the case as incorrect and says so."""
    if not answer.strip():
        return Verdict(False, "empty answer")
    llm = llm or get_llm()
    prompt = llm.load_prompt(
        "judge_answer",
        question=question,
        answer=answer,
        reference=reference[:_MAX_REFERENCE_CHARS],
    )
    try:
        data = llm.generate_json(prompt, schema=JUDGE_SCHEMA, model=get_settings().model_lite)
    except LLMError as exc:
        return Verdict(False, f"judge failed: {exc}")
    return Verdict(bool(data.get("correct")), str(data.get("reason", "")).strip())
