"""Evidence pages → a cited answer, or an honest NOT_FOUND (principle P6)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from libkb.config import Settings, get_settings
from libkb.library.models import PageContent
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "sufficient": {"type": "boolean"},
        # A one-line first-person "thought" shown in the UI (D-061): what the answerer
        # concluded, in its own voice. Rides on this call (near-free); a miss fails open.
        "thought": {"type": "string"},
    },
    "required": ["answer", "confidence", "sufficient"],
}

# Same schema, plus the verbatim quotes the cite-or-abstain gate verifies (D-055).
ANSWER_SCHEMA_CITE = {
    "type": "object",
    "properties": {
        **ANSWER_SCHEMA["properties"],
        "quotes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [*ANSWER_SCHEMA["required"], "quotes"],
}

SUFFICIENCY_SCHEMA = {
    "type": "object",
    "properties": {"sufficient": {"type": "boolean"}, "missing": {"type": "string"}},
    "required": ["sufficient"],
}

_WS = re.compile(r"\s+")


def _sufficient(query: str, blocks: str, llm: LLM, model: str) -> tuple[bool, str]:
    """Is the evidence ENOUGH to answer — not merely about the right subject? (D-056)

    The measured failure this exists for: handed on-topic-but-insufficient pages, the answerer grows
    MORE confident and improvises (a documented RAG paradox — extra context suppresses abstention).
    Cite-or-abstain could not catch it because the model quotes REAL sentences and then synthesises
    past them; the question was never "does a quote exist" but "is there enough here". Judged BEFORE
    generation, on the lite tier, so an insufficient context costs one cheap call and no answer.

    Fails OPEN (returns sufficient) if the check itself errors: a broken gate must not silence a
    library that can answer — the downstream `sufficient`/citation gates still apply."""
    try:
        prompt = llm.load_prompt("sufficiency", query=query, evidence=blocks)
        data = llm.generate_json(prompt, schema=SUFFICIENCY_SCHEMA, model=model)
    except Exception:
        return True, ""
    return bool(data.get("sufficient", True)), str(data.get("missing") or "").strip()


def _norm(s: str) -> str:
    """Whitespace-insensitive, case-folded, width-normalised — a quote that differs from the source
    only by spacing, line breaks, or full-width forms (３０％ vs 30%, routine in Japanese text) must
    still count as present."""
    return _WS.sub("", unicodedata.normalize("NFKC", s)).lower()


# A figure the answer asserts: a number, optionally carrying a unit. These are what the audit caught
# being invented ("30%引き", "1.5倍", "±2℃") — and unlike prose, a figure is CHECKABLE IN CODE.
_FIGURE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(%|倍|℃|°c|円|日間|日|週間|週|ヶ月|か月|カ月|年|点|個)?", re.I
)


def _invented_figures(answer: str, evidence_norm: str) -> list[str]:
    """Every figure the answer states that appears NOWHERE in the evidence (D-057).

    Bare small integers are skipped: they are list markers ("1.", "2.") and trivial counts, not
    claims, and flagging them would fight the model over formatting. A figure WITH a unit, a
    decimal, or a value >= 10 is a claim about the world — and if the evidence never says it, the
    model made it up. This is the model-independent half of the spec-B gate: prose is arguable, a
    number is not.
    """
    bad: list[str] = []
    for m in _FIGURE.finditer(unicodedata.normalize("NFKC", answer)):
        num, unit = m.group(1), (m.group(2) or "")
        if not unit and "." not in num and float(num) < 10:
            continue
        token = _norm(num + unit)
        if token and token not in evidence_norm and num not in bad:
            bad.append(num + unit)
    return bad


def _grounded(quote: str, evidence_norm: str, *, w: int = 12, thresh: float = 0.5) -> bool:
    """Is `quote` really in the evidence — verified by CODE, not the model's say-so (D-055)?

    Exact-substring first (the honest case). Otherwise, character n-gram overlap: a genuine quote a
    model lightly reformatted still shares most of its 12-char shingles with the source; a made-up
    one shares almost none. Char-level (not word) because it must work for Japanese, which has no
    spaces. A quote too short to verify does not count — it is too easy to match by accident."""
    q = _norm(quote)
    if len(q) < 10:
        return False
    if q in evidence_norm:
        return True
    grams = [q[i : i + w] for i in range(len(q) - w + 1)]
    if not grams:
        return False
    hits = sum(1 for g in grams if g in evidence_norm)
    return hits / len(grams) >= thresh


# The confidence gate is ORDINAL: `medium` demands the model rule out `low`; `high` demands it rule
# out `low` and `medium`. Anything the model returns outside the enum is treated as `medium` — the
# schema constrains it, but a gate must not crash on a surprise value.
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


@dataclass
class Citation:
    path: str
    page_id: str
    quote: str | None = None


@dataclass
class Answer:
    text: str
    status: str = "answered"  # answered | not_found
    confidence: str = "medium"
    citations: list[Citation] = field(default_factory=list)
    # figures the anti-fabrication gate (D-057) found in a draft answer and removed — surfaced so
    # the UI can show "2 invented numbers removed" — the model-independent honesty signal, visible.
    stripped: list[str] = field(default_factory=list)
    # the answerer's one-line first-person "thought" (D-061), narrated to the thinking timeline.
    thought: str = ""


def compose_answer(
    query: str,
    pages: list[PageContent],
    store: LibraryStore,
    *,
    llm: LLM | None = None,
    min_confidence: str | None = None,
    settings: Settings | None = None,
) -> Answer:
    """Answer strictly from the read pages. Insufficient evidence → not_found status.

    `settings` lets a caller pass a per-REQUEST override (the API builds one from the UI's option
    panel, so depth/basket/gates ride with the query the way the model already does) instead of the
    process-wide singleton. `min_confidence` (default from Settings) is the honesty gate that is
    SEPARATE from the basket size (D-043)."""
    llm = llm or get_llm()
    settings = settings or get_settings()
    min_confidence = min_confidence or settings.cascade_min_confidence
    require_citation = settings.answer_require_citation
    blocks = "\n\n".join(
        f"[EVIDENCE {i + 1} — {store.path_str(p.page_id)}]\n<<<\n{p.markdown}\n>>>"
        for i, p in enumerate(pages)
    )
    # SUFFICIENCY gate (D-056) — runs FIRST and cheapest: if the evidence is merely on-topic rather
    # than enough, abstain now and never pay for the answer call at all.
    if settings.answer_sufficiency_gate:
        ok, missing = _sufficient(query, blocks, llm, settings.model_lite)
        if not ok:
            closest = [store.path_str(p.page_id) for p in pages]
            return compose_not_found(query, closest, note=missing)

    # cite-or-abstain (D-055): only when the gate is on does the answerer owe verbatim quotes, and
    # only then do the prompt/schema ask for them — off is byte-for-byte the old behaviour.
    cite = llm.load_prompt("answer_cite") if require_citation else ""
    cite_json = ', "quotes": string[]' if require_citation else ""
    ban = settings.answer_ban_invented_specifics
    synth = llm.load_prompt("answer_synthesis") if ban else ""
    # persona is the ONE place the librarian's behaviour/honesty rules live (D-059) — always on.
    persona = llm.load_prompt("persona")
    prompt = llm.load_prompt(
        "answer",
        query=query,
        evidence=blocks,
        persona=persona,
        cite=cite,
        cite_json=cite_json,
        synth=synth,
    )
    schema = ANSWER_SCHEMA_CITE if require_citation else ANSWER_SCHEMA
    data = llm.generate_json(prompt, schema=schema)

    # SPEC B (D-057): licensing synthesis is not licensing invention. Every figure in the answer
    # must exist in the evidence; the ones that do not were made up, so name them and demand a
    # rewrite. One retry only — a correction, not a negotiation; a second miss is not looped on.
    stripped: list[str] = []
    if ban:
        evidence_norm = _norm("\n".join(p.markdown for p in pages))
        invented = _invented_figures(str(data.get("answer") or ""), evidence_norm)
        if invented:
            fix = llm.load_prompt("answer_fix_specifics", bad="\n".join(f"- {b}" for b in invented))
            data = llm.generate_json(prompt + "\n\n" + fix, schema=schema)
            stripped = invented  # surfaced on the Answer so the UI can show what was removed

    citations = [Citation(path=store.path_str(p.page_id), page_id=p.page_id) for p in pages]
    text = str(data.get("answer") or "").strip()
    confidence = str(data.get("confidence") or "medium")
    thought = str(data.get("thought") or "").strip()  # narrated to the timeline (D-061)

    # `sufficient` is the model's word, and P6 does not run on the model's word alone. An "answer"
    # of `"J"` is not an answer; MEASURED, 40 of 301 unanswerable questions came back exactly like
    # that, each one carrying `"sufficient": true`. The generate_json repair path was fabricating
    # them (fixed in llm/client.py) — but the guard belongs HERE too, because this is the function
    # that decides whether the library speaks or stays silent, and it must fail towards silence.
    #
    # The floor is a CHARACTER count, not a word count, and it is deliberately low: MultiHop's
    # comparison questions are answered "Yes" and "No", and those are correct, complete answers. Two
    # characters is the shortest true thing this library can say.
    if not data.get("sufficient", True) or len(text) < 2:
        closest = [store.path_str(p.page_id) for p in pages]
        return compose_not_found(query, closest, note=text)

    # CITE-OR-ABSTAIN (D-055). The model said "sufficient" and wrote an answer — but on an in-domain
    # question whose answer is NOT in the (plausible-looking) evidence, that is exactly where it
    # improvises. So demand PROOF: at least one quote it returned must actually appear in the
    # evidence, verified in code. No grounded quote ⇒ answer not backed by the pages ⇒ NOT_FOUND.
    if require_citation:
        evidence_norm = _norm("\n".join(p.markdown for p in pages))
        grounded = [q for q in (data.get("quotes") or []) if _grounded(str(q), evidence_norm)]
        if not grounded:
            closest = [store.path_str(p.page_id) for p in pages]
            return compose_not_found(query, closest, note=text)
        citations = [
            Citation(path=c.path, page_id=c.page_id, quote=grounded[0] if i == 0 else None)
            for i, c in enumerate(citations)
        ]

    # The SEPARATE honesty gate (D-043). The model said "sufficient", but if it can only muster a
    # confidence below what the caller demands, the library stays silent. This is the knob that lets
    # the basket grow for multi-hop accuracy without dragging the improvisation rate up with it —
    # the two used to be one dial (`cascade_max_pages`), and only the n=301 run separated them.
    if _CONFIDENCE_RANK.get(confidence, 1) < _CONFIDENCE_RANK.get(min_confidence, 0):
        closest = [store.path_str(p.page_id) for p in pages]
        return compose_not_found(query, closest, note=text)
    return Answer(
        text=text,
        status="answered",
        confidence=confidence,
        citations=citations,
        stripped=stripped,
        thought=thought,
    )


def compose_not_found(query: str, closest: list[str], *, note: str = "") -> Answer:
    """A designed not-found outcome — never a guess (P6)."""
    lines = ["The library doesn't hold an answer to this yet."]
    if note:
        lines.append(note.strip())
    if closest:
        lines.append("Closest shelves: " + " · ".join(closest) + ".")
    lines.append("You could ingest a document on this topic to fill the gap.")
    return Answer(text="\n\n".join(lines), status="not_found", confidence="low", citations=[])
