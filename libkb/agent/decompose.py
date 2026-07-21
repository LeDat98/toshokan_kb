"""Query DECOMPOSITION for compound multi-hop questions (the decompose route).

The measured problem (SCORECARD §2.3/§3): a compound question — "compare the refund policy BEFORE
and AFTER the March 2025 change, and which applies to international orders" — bundles several
DISTINCT needs. Embedding the whole thing gives ONE blurred query vector that ranks none of the
parts' pages reliably into a small basket. The sieve is not the bottleneck (it has ALL the evidence
in its top-20 for 93.5% of MultiHop questions); the single blurred query is. So comparison/temporal
questions sit at ~60–70% while single-hop inference is ~94%.

The fix attacks the RETRIEVAL layer, not the selection layer (the earlier `triage_coverage` attempt
fixed the wrong layer and was refuted, D-051):

    ① SPLIT     1 lite call  break the question into STANDALONE sub-questions (in the route)
    ② RETRIEVE  0 LLM        look each sub-question up SHARPLY and IN PARALLEL — each gets its own
                            focused query, so its target page ranks high in its own small basket
    ③ COMBINE   1 strong     hand the UNION of evidence, grouped by sub-question, to one answer call
                            that reasons ACROSS the parts (compare, apply conditions), cited; an
                            empty union is an honest NOT_FOUND.

This is the "decompose → parallel retrieve → combine context → generate" orchestration (the AWS
Lambda/Step-Functions pattern), home-grown: `parallel_map` is the fan-out, the registry route is the
seam. Cheaper than the synthesizer for compound questions — no per-page LLM map, just N sharp
retrievals and one combine.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

from libkb.agent.answerer import Answer, Citation, compose_not_found
from libkb.agent.navigator import NavResult
from libkb.agent.tools import NavEvent
from libkb.catalog.search import lookup
from libkb.catalog.store import Catalog
from libkb.concurrency import parallel_map
from libkb.config import Settings, get_settings
from libkb.exceptions import NodeNotFound
from libkb.library.models import PageContent
from libkb.library.sections import pick_sections
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)

EventCB = Callable[[NavEvent], None]

# The combined answer — same honesty fields as the answerer/synthesizer: `sufficient` lets it stop,
# `thought` is the first-person line narrated to the timeline (D-061).
COMBINE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "sufficient": {"type": "boolean"},
        "thought": {"type": "string"},
    },
    "required": ["answer", "confidence", "sufficient"],
}


@dataclass
class SubEvidence:
    question: str
    pages: list[PageContent]


@dataclass
class DecomposeResult:
    answer: Answer
    nav: NavResult  # same shape the cascade/synthesizer return, so callers + the eval are unchanged
    sub_questions: list[str] = field(default_factory=list)


def decompose_answer(
    query: str,
    sub_questions: list[str],
    *,
    store: LibraryStore,
    catalog: Catalog,
    llm: LLM | None = None,
    settings: Settings | None = None,
    event_cb: EventCB | None = None,
) -> DecomposeResult:
    """Retrieve each sub-question sharply in parallel, then combine the union into one answer."""
    llm = llm or get_llm()
    s = settings or get_settings()
    events: list[NavEvent] = []

    def emit(event: NavEvent) -> None:
        events.append(event)
        if event_cb:
            event_cb(event)

    emit(
        NavEvent(
            "thought",
            f"This is a compound question — splitting it into {len(sub_questions)} parts and "
            "looking each one up on its own.",
            None,
            None,
            "done",
            detail="decompose",
        )
    )

    # ② RETRIEVE — one SHARP query per sub-question, in parallel (the Step-Functions "Map" fan-out).
    def _retrieve(subq: str) -> SubEvidence:
        hits = lookup(catalog, subq, llm=llm, top_k=s.decompose_per_q)
        pages: list[PageContent] = []
        for hit in hits[: s.decompose_per_q]:
            try:
                page = store.page(hit.page_id)
            except NodeNotFound:
                continue  # a stale catalog row must not break a sub-query
            body = pick_sections(page.markdown, [], max_tokens=s.decompose_max_page_tokens)
            pages.append(page.model_copy(update={"markdown": body}))
        return SubEvidence(question=subq, pages=pages)

    subs = parallel_map(_retrieve, sub_questions, workers=s.decompose_concurrency)
    for se in subs:
        emit(
            NavEvent(
                "lookup",
                se.question[:70],
                None,
                None,
                "done" if se.pages else "notfound",
                detail=f"{len(se.pages)} page(s)",
            )
        )

    # Union the pages for citations; KEEP the per-sub-question grouping for the combine prompt.
    union: dict[str, PageContent] = {}
    for se in subs:
        for page in se.pages:
            union.setdefault(page.page_id, page)
    if not union:
        return _nothing(query, events)

    emit(
        NavEvent(
            "read",
            f"reading evidence for {len(sub_questions)} parts",
            None,
            None,
            "read",
            detail=f"{len(union)} page(s)",
        )
    )
    emit(NavEvent("compose", "combining the parts into one answer", None, None, "walking"))

    # ③ COMBINE — evidence grouped by sub-question, so the answer can reason across the parts.
    blocks: list[str] = []
    for i, se in enumerate(subs, 1):
        blocks.append(f"### Sub-question {i}: {se.question}")
        if not se.pages:
            blocks.append("(no evidence found for this part)")
        for page in se.pages:
            blocks.append(f"[EVIDENCE — {store.path_str(page.page_id)}]\n<<<\n{page.markdown}\n>>>")
    evidence = "\n\n".join(blocks)

    persona = llm.load_prompt("persona")  # the one place the honesty/voice rules live (D-059)
    try:
        data = llm.generate_json(
            llm.load_prompt("decompose_combine", query=query, evidence=evidence, persona=persona),
            schema=COMBINE_SCHEMA,
        )
    except Exception as exc:  # noqa: BLE001 — a failed combine is a NOT_FOUND, never a crash (P6)
        log.warning("decompose_combine_failed", error=str(exc))
        return _nothing(query, events, [store.path_str(pid) for pid in list(union)[:5]])

    text = str(data.get("answer") or "").strip()
    if not data.get("sufficient", True) or len(text) < 2:  # fail towards silence
        return _nothing(query, events, [store.path_str(pid) for pid in list(union)[:5]], note=text)

    pages = list(union.values())
    citations = [Citation(path=store.path_str(pid), page_id=pid) for pid in union]
    thought = str(data.get("thought") or "").strip()
    if thought:
        emit(NavEvent("thought", thought, None, None, "done", detail="answer"))
    emit(
        NavEvent(
            "found", "FOUND", None, None, "found", detail=f"combined {len(sub_questions)} parts"
        )
    )
    answer = Answer(
        text=text,
        status="answered",
        confidence=str(data.get("confidence") or "medium"),
        citations=citations,
        thought=thought,
    )
    nav = NavResult(
        status="FOUND",
        pages=pages,
        hops=len(sub_questions),  # a "hop" here is a sub-question that fed the combined answer
        reason="decompose",
        events=events,
    )
    log.info("decompose_done", sub_questions=len(sub_questions), pages=len(union))
    return DecomposeResult(answer=answer, nav=nav, sub_questions=sub_questions)


def _nothing(
    query: str, events: list[NavEvent], closest: list[str] | None = None, note: str = ""
) -> DecomposeResult:
    events.append(NavEvent("not_found", "NOT FOUND", None, None, "notfound"))
    closest = closest or []
    return DecomposeResult(
        answer=compose_not_found(query, closest, note=note),
        nav=NavResult(status="NOT_FOUND", closest=closest, reason="decompose", events=events),
    )
