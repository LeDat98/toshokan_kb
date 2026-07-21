"""The synthesizer ROUTE (D-061): the front door for AGGREGATIVE questions — ones whose answer is a
synthesis across MANY pages, which the cascade's small basket cannot reach (MultiHop measured this).

The route makes ONE lite call to decide whether the question is genuinely aggregative and, if so,
which scope (a domain/shelf) it is confined to. A single-fact question returns None and DEFERS to
the library's default path — so a mis-route (the router sending an ordinary question here) is
caught, the same double-safety the calculator/catalog/clarify routes have. The heavy map-reduce
lives in `libkb.agent.synthesizer`; this file only decides to run it and resolves the scope.
"""

from __future__ import annotations

from libkb.agent.roles.base import AgentCard
from libkb.agent.roles.catalog_nav import _descendants, _find
from libkb.agent.roles.routes import RouteContext
from libkb.agent.synthesizer import synthesize
from libkb.catalog.store import Catalog
from libkb.config import Settings
from libkb.llm.client import get_llm

DETECT_SCHEMA = {
    "type": "object",
    "properties": {
        "aggregative": {"type": "boolean"},
        "scope": {"type": "string"},
    },
    "required": ["aggregative"],
}


def _open_catalog(settings: Settings) -> Catalog | None:
    """Open the on-disk catalog if it exists — the route runs BEFORE the orchestrator opens its own,
    so it owns this one and closes it. None ⇒ no index to synthesise from; defer to the walk."""
    if not settings.db_path.exists():
        return None
    try:
        return Catalog(settings.db_path)
    except Exception:
        return None


def _resolve_scope(store, name: str) -> tuple[set[str] | None, str]:
    """Turn a scope NAME ('AI-News', 'RAG') into the set of page_ids under it, for the scan. An
    unknown name scans the whole library (best-effort — the scan is a sieve, not a gate)."""
    if not name.strip():
        return None, ""
    node = _find(store, name)
    if node is None:
        return None, ""
    ids = {n.id for n in _descendants(store, node.id, "page")}
    return (ids or None), node.title


class SynthesizerRoute:
    card = AgentCard(
        id="synthesize",
        name="Cross-document synthesis",
        description="Answers AGGREGATIVE questions that span many pages — 'what techniques appear "
        "across the library', 'trends in X', 'compare how the books approach Y' — by scanning wide "
        "and map-reducing, where the cascade's small basket cannot reach.",
        skills=["synthesize", "aggregate", "survey"],
        route_when="an AGGREGATIVE question spanning MANY documents — 'what are the common/all X', "
        "'trends across Y', 'compare how everything approaches Z', 'summarise the whole D domain'; "
        "NOT a single-fact question (that is search_library)",
    )

    def handle(self, ctx: RouteContext):
        llm = ctx.llm or get_llm()
        try:
            data = llm.generate_json(
                llm.load_prompt("synth_detect", query=ctx.query),
                schema=DETECT_SCHEMA,
                model=ctx.settings.model_lite,
            )
        except Exception:
            return None
        if not data.get("aggregative"):
            return None  # a single-fact question → defer to the cascade (cheaper and sharper)

        within, label = _resolve_scope(ctx.store, str(data.get("scope") or ""))
        catalog = _open_catalog(ctx.settings)
        if catalog is None:
            return None  # no index → let the default knowledge path handle it
        try:
            result = synthesize(
                ctx.query,
                store=ctx.store,
                catalog=catalog,
                llm=ctx.llm,
                settings=ctx.settings,
                event_cb=ctx.emit,
                within=within,
                scope_label=label,
            )
        finally:
            catalog.close()
        return result.answer, result.nav
