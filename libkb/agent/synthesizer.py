"""Cross-document SYNTHESIS by map-reduce (the P3.7 synthesizer, D-061).

The cascade answers "what does the library SAY about topic X" by opening a small basket (~10 pages)
and reading sections. It cannot answer AGGREGATIVE questions — "what techniques appear across the
library", "trends in the AI-news domain", "compare how the books approach chunking" — because those
need EVERY relevant page, not the best ten. MultiHop measured exactly this: the cascade cannot reach
past its basket, and no single index answers a "trends across all X" question.

So this is a different retrieval SHAPE, chosen by the router only when the question is aggregative:

    ① SCAN    0 LLM calls   embed the question, take a WIDE net (`synth_coverage_n` pages),
                            optionally bounded to a named scope (a domain/shelf) — a sieve, not a
                            basket.
    ② MAP     N lite calls  read each of the top `synth_map_n` pages (bounded, TRUNCATED, and
                            CONCURRENT) and extract the ONE finding it contributes; drop the pages
                            that contribute nothing. This is the expensive step, so it is lite-tier.
    ③ REDUCE  1 strong call combine the findings — COMPACT, not full pages — into one cited answer;
                            no findings ⇒ an honest NOT_FOUND (P6).

Honesty is preserved the way the cascade preserves it: every finding is read from a real page body
(never the model's memory), the answer is synthesised ONLY from those findings, it CITES the pages
that contributed, and an empty harvest is an honest NOT_FOUND. The cost is EARNED — it runs only on
questions the cascade provably cannot answer — and BOUNDED: the map reads on the lite tier,
truncated, and in parallel (D-047), so a 12-page synthesis is a handful of cheap calls, not twelve
strong ones. The reduce sees the findings, never the full pages, so its bill does not grow with the
size of the scan.
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
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)

EventCB = Callable[[NavEvent], None]

# What ONE page contributes to the question. `relevant=false` drops it from the synthesis entirely.
MAP_SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "finding": {"type": "string"},
    },
    "required": ["relevant"],
}

# The combined answer. Same honesty fields as the answerer: `sufficient` lets the reducer abstain,
# `thought` is the first-person line narrated to the timeline (D-061).
REDUCE_SCHEMA = {
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
class Finding:
    page_id: str
    path: str
    text: str


@dataclass
class SynthResult:
    answer: Answer
    nav: NavResult  # the same shape the cascade/walk return, so callers and the eval are unchanged
    findings: list[Finding] = field(default_factory=list)


def synthesize(
    query: str,
    *,
    store: LibraryStore,
    catalog: Catalog,
    llm: LLM | None = None,
    settings: Settings | None = None,
    event_cb: EventCB | None = None,
    within: set[str] | None = None,
    scope_label: str = "",
) -> SynthResult:
    """Answer an aggregative question by scanning wide, mapping each to a finding, then reducing.

    `within` restricts the scan to a set of page_ids (a named domain/shelf); `scope_label` is that
    scope's title, for the narration only. Both default to the whole library.
    """
    llm = llm or get_llm()
    s = settings or get_settings()
    events: list[NavEvent] = []

    def emit(event: NavEvent) -> None:
        events.append(event)
        if event_cb:
            event_cb(event)

    scope_note = f" in {scope_label}" if scope_label else ""

    # ① SCAN — a wide net, free. No gate: a sieve is allowed to be unsure (the map reads verify it).
    ranked = lookup(catalog, query, llm=llm, top_k=s.synth_coverage_n, within=within)
    if not ranked:
        emit(NavEvent("lookup", "card catalog", None, None, "notfound", detail="no candidates"))
        return _nothing(query, events)
    emit(
        NavEvent(
            "lookup",
            "card catalog",
            None,
            None,
            "done",
            detail=f"{len(ranked)} pages scanned{scope_note}",
        )
    )

    shortlist = ranked[: s.synth_map_n]
    emit(
        NavEvent(
            "read",
            f"reading across {len(shortlist)} pages",
            None,
            None,
            "read",
            detail="one pass each, in parallel",
        )
    )

    # ② MAP — read each page, extract its contribution. Lite tier, truncated, CONCURRENT (D-047).
    # A page that fails to open (stale row) or contributes nothing returns None and is dropped; one
    # bad page must never sink the whole survey.
    def _map_one(hit) -> Finding | None:
        try:
            page = store.page(hit.page_id)
        except NodeNotFound:
            return None
        body = f"{page.title}\n\n{page.markdown}".strip()[: s.synth_map_chars]
        try:
            data = llm.generate_json(
                llm.load_prompt("synth_map", query=query, document=body),
                schema=MAP_SCHEMA,
                model=s.model_lite,
            )
        except Exception:
            return None  # a dropped map is a lost page, not a failed query
        if not data.get("relevant"):
            return None
        text = str(data.get("finding") or "").strip()
        if not text:
            return None
        return Finding(page_id=hit.page_id, path=store.path_str(hit.page_id), text=text)

    mapped = parallel_map(_map_one, shortlist, workers=s.synth_concurrency)
    findings = [f for f in mapped if f is not None]
    if not findings:
        # Scanned wide and nothing contributed — an honest NOT_FOUND, with the closest pages named.
        closest = [store.path_str(h.page_id) for h in shortlist[:5]]
        return _nothing(query, events, closest)

    emit(
        NavEvent(
            "thought",
            f"{len(findings)} of {len(shortlist)} pages had something to add — "
            "synthesising across them.",
            None,
            None,
            "done",
            detail="synthesize",
        )
    )

    # ③ REDUCE — combine the COMPACT findings into one cited answer. The reducer sees findings,
    # never full pages, so its bill is independent of how wide we scanned.
    blocks = "\n\n".join(f"[FINDING {i + 1} — {f.path}]\n{f.text}" for i, f in enumerate(findings))
    emit(NavEvent("compose", "synthesising across the findings", None, None, "walking"))
    persona = llm.load_prompt("persona")  # the one place the honesty/voice rules live (D-059)
    try:
        data = llm.generate_json(
            llm.load_prompt("synth_reduce", query=query, findings=blocks, persona=persona),
            schema=REDUCE_SCHEMA,
        )
    except Exception as exc:  # noqa: BLE001 — a failed reduce is a NOT_FOUND, never a crash (P6)
        log.warning("synth_reduce_failed", error=str(exc))
        return _nothing(query, events, [f.path for f in findings[:5]])

    text = str(data.get("answer") or "").strip()
    # Fail towards silence: the reducer must both say "sufficient" and actually write something.
    if not data.get("sufficient", True) or len(text) < 2:
        return _nothing(query, events, [f.path for f in findings[:5]], note=text)

    # The contributing pages, re-read from the store for citations + the trace panel. These are
    # metadata only — they are NEVER sent to any LLM (the reduce already ran on the findings), so
    # this cannot re-inflate the token bill the map-reduce exists to avoid.
    pages = []
    for f in findings:
        try:
            pages.append(store.page(f.page_id))
        except NodeNotFound:
            continue
    citations = [Citation(path=f.path, page_id=f.page_id) for f in findings]
    thought = str(data.get("thought") or "").strip()
    if thought:
        emit(NavEvent("thought", thought, None, None, "done", detail="answer"))
    emit(
        NavEvent(
            "found",
            "FOUND",
            None,
            None,
            "found",
            detail=f"synthesised {len(findings)} sources",
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
        hops=len(findings),  # a "hop" here is a source that contributed to the synthesis
        reason="synthesize",
        events=events,
    )
    log.info("synth_done", scanned=len(shortlist), findings=len(findings))
    return SynthResult(answer=answer, nav=nav, findings=findings)


def _nothing(
    query: str, events: list[NavEvent], closest: list[str] | None = None, note: str = ""
) -> SynthResult:
    events.append(NavEvent("not_found", "NOT FOUND", None, None, "notfound"))
    closest = closest or []
    return SynthResult(
        answer=compose_not_found(query, closest, note=note),
        nav=NavResult(status="NOT_FOUND", closest=closest, reason="synthesize", events=events),
    )
