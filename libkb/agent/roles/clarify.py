"""The clarify ROUTE (D-061): when a message is clearly too vague to act on, ask ONE targeted
question instead of guessing — friendlier, and honest (it does not fabricate a referent).

Conservative by design: the model double-checks the message is genuinely ambiguous, and the route
DEFERS to the library (returns None) whenever the message is answerable even loosely — so a real
question is never turned into a needless question back."""

from __future__ import annotations

from libkb.agent.answerer import Answer
from libkb.agent.navigator import NavResult
from libkb.agent.roles.base import AgentCard
from libkb.agent.roles.routes import RouteContext
from libkb.agent.tools import NavEvent
from libkb.llm.client import get_llm

CLARIFY_SCHEMA = {
    "type": "object",
    "properties": {"ambiguous": {"type": "boolean"}, "question": {"type": "string"}},
    "required": ["ambiguous"],
}


class ClarifyRoute:
    card = AgentCard(
        id="clarify",
        name="Ask to clarify",
        description="When a message is clearly too vague to act on, asks ONE short clarifying "
        "question instead of guessing.",
        skills=["clarify"],
        route_when="the message is clearly too vague to act on — a pronoun with no referent ('tell "
        "me about it'), a bare fragment, or 'compare/versus' with nothing named",
    )

    def handle(self, ctx: RouteContext) -> tuple[Answer, NavResult] | None:
        llm = ctx.llm or get_llm()
        try:
            data = llm.generate_json(
                llm.load_prompt("clarify", query=ctx.query),
                schema=CLARIFY_SCHEMA,
                model=ctx.settings.model_lite,
            )
        except Exception:
            return None
        if not data.get("ambiguous"):
            return None  # answerable as-is → defer to the library
        question = str(data.get("question") or "").strip()
        if not question:
            return None
        events = [
            NavEvent(
                "thought",
                "This is ambiguous — asking a quick question before searching.",
                None,
                None,
                "done",
                detail="route",
            ),
            NavEvent("found", "asked to clarify", None, None, "found", detail="clarify"),
        ]
        if ctx.emit:
            for ev in events:
                ctx.emit(ev)
        answer = Answer(text=question, status="answered", confidence="medium")
        return answer, NavResult(status="FOUND", reason="clarify", events=events)
