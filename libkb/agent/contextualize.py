"""History-aware query rewriting — the ONE place a conversation touches retrieval (D-061 follow-up).

The founding constraint stands: the cascade is single-shot, and the whole retrieval redesign exists
to AVOID resending a conversation every turn (the walk's O(T²) bill). So multi-turn is not bought by
feeding history into the answer prompt — it is bought here, cheaply: a lite call reads the last few
turns and, if the new message is a FOLLOW-UP ("tell me more about it", "and in Japanese?"), rewrites
it into a STANDALONE question. The cascade then runs on that standalone query exactly as before —
history has already done its job and never enters the expensive calls.

Conservative and fail-open by design: a self-contained question is returned UNCHANGED (no rewrite),
and any error falls back to the original query — a broken contextualizer must never cost an answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from libkb.config import Settings
from libkb.llm.client import LLM

CONTEXT_SCHEMA = {
    "type": "object",
    "properties": {
        "followup": {"type": "boolean"},
        "standalone": {"type": "string"},
    },
    "required": ["followup"],
}

# Each turn is truncated before it enters the rewrite prompt — the contextualizer needs the recent
# GIST to resolve a pronoun, not the full text of a long answer (that would defeat the point).
_SNIPPET_CHARS = 400


def _render(history: list[dict], turns: int) -> str:
    lines = []
    for m in history[-turns:]:
        role = str(m.get("role", "")).strip() or "user"
        text = str(m.get("text", "")).strip().replace("\n", " ")
        if len(text) > _SNIPPET_CHARS:
            text = text[:_SNIPPET_CHARS] + "…"
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


@dataclass
class ContextResult:
    query: str  # what to RETRIEVE with — the rewritten standalone query, or the original unchanged
    rewritten: bool
    original: str
    thought: str = ""  # a first-person line for the timeline when a rewrite happened (D-061)


def contextualize(query: str, history: list[dict], llm: LLM, settings: Settings) -> ContextResult:
    """Rewrite a follow-up into a standalone query using recent history; else return it unchanged.

    `history` is the PRIOR turns (not the current message), oldest → newest, each `{role, text}`.
    """
    if not history:
        return ContextResult(query=query, rewritten=False, original=query)
    try:
        convo = _render(history, settings.context_history_turns)
        data = llm.generate_json(
            llm.load_prompt("contextualize", history=convo, query=query),
            schema=CONTEXT_SCHEMA,
            model=settings.model_lite,
        )
    except Exception:
        return ContextResult(query=query, rewritten=False, original=query)  # fail open

    if not data.get("followup"):
        return ContextResult(query=query, rewritten=False, original=query)
    standalone = str(data.get("standalone") or "").strip()
    if not standalone or standalone == query:
        return ContextResult(query=query, rewritten=False, original=query)
    return ContextResult(
        query=standalone,
        rewritten=True,
        original=query,
        thought=f'Reading this as a follow-up — searching for: "{standalone}".',
    )
