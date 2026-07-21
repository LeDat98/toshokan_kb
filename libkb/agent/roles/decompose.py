"""The decompose ROUTE: the front door for COMPOUND multi-hop questions — ones that bundle several
distinct information needs ("compare A before vs after X, and which applies to B"). The route makes
ONE lite call to split the question into standalone sub-questions; the heavy fan-out lives in
`libkb.agent.decompose`.

Defer-safe like the other routes: a question that is not genuinely compound (or splits into <2 real
sub-questions) returns None and falls through to the cascade — so a mis-route never turns a simple
question into a needlessly expensive one. Distinct from `synthesize`: decompose answers a question
with a FIXED SET of named sub-parts (compare/condition); synthesize surveys an open-ended "trends
across all X".
"""

from __future__ import annotations

from libkb.agent.decompose import decompose_answer
from libkb.agent.roles.base import AgentCard
from libkb.agent.roles.routes import RouteContext
from libkb.agent.roles.synthesizer import _open_catalog
from libkb.llm.client import get_llm

SPLIT_SCHEMA = {
    "type": "object",
    "properties": {
        "compound": {"type": "boolean"},
        "sub_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["compound"],
}


class DecomposeRoute:
    card = AgentCard(
        id="decompose",
        name="Decompose & combine",
        description="Answers COMPOUND questions that bundle several distinct sub-questions — "
        "'compare A before vs after X, and which applies to B' — by looking each sub-question up "
        "separately and combining the evidence before answering.",
        skills=["decompose", "multi-hop", "compare"],
        route_when="a COMPOUND question bundling 2+ DISTINCT sub-questions to look up separately "
        "then combine — 'compare A before vs after the change, and which applies to B'; NOT a "
        "single-fact question, and NOT an open-ended 'trends across all X' (that is synthesize)",
    )

    def handle(self, ctx: RouteContext):
        llm = ctx.llm or get_llm()
        try:
            data = llm.generate_json(
                llm.load_prompt(
                    "decompose_split", query=ctx.query, max_subqs=ctx.settings.decompose_max_subqs
                ),
                schema=SPLIT_SCHEMA,
                model=ctx.settings.model_lite,
            )
        except Exception:
            return None
        if not data.get("compound"):
            return None  # a single-need question → defer to the cascade
        subs = [str(x).strip() for x in (data.get("sub_questions") or []) if str(x).strip()]
        if len(subs) < 2:
            return None  # not really compound → defer
        subs = subs[: ctx.settings.decompose_max_subqs]

        catalog = _open_catalog(ctx.settings)
        if catalog is None:
            return None  # no index → let the default knowledge path handle it
        try:
            result = decompose_answer(
                ctx.query,
                subs,
                store=ctx.store,
                catalog=catalog,
                llm=ctx.llm,
                settings=ctx.settings,
                event_cb=ctx.emit,
            )
        finally:
            catalog.close()
        return result.answer, result.nav
