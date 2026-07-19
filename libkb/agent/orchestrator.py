"""Entry point: dispatch a query to a walk, then compose the answer.

P2c adds a catalog fast path in front of the walk: if the card catalog matches the question
with high confidence, answer straight from those pages — but only if the answerer judges the
evidence sufficient; otherwise fall back to a full walk. The walk itself also gets the
`ask_librarian` tool when a catalog is present. The front-door classifier and synthesis
strategies still arrive in P3 (see docs/ARCHITECTURE.md).
"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from dataclasses import dataclass

import structlog

from libkb.agent.answerer import Answer, compose_answer, compose_not_found
from libkb.agent.navigator import NavResult, navigate
from libkb.agent.tools import NavEvent
from libkb.catalog.search import lookup
from libkb.catalog.store import Catalog
from libkb.config import Settings, get_settings
from libkb.exceptions import LLMError, NodeNotFound
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

log = structlog.get_logger(__name__)

EventCB = Callable[[NavEvent], None]


@dataclass
class QueryResult:
    answer: Answer
    nav: NavResult


def answer_query(
    query: str,
    *,
    store: LibraryStore | None = None,
    catalog: Catalog | None = None,
    llm: LLM | None = None,
    event_cb: EventCB | None = None,
    shortcut: bool = True,
    use_catalog: bool = True,
    settings: Settings | None = None,
) -> QueryResult:
    """`shortcut=False` still lets the walk consult the catalog via ask_librarian.
    `use_catalog=False` removes the catalog entirely — that is the eval's pure `walk` arm.
    `settings` is a per-REQUEST override (the API builds one from the UI option panel) so retrieval
    depth / basket / answer gates ride with the query, exactly as the model already does."""
    settings = settings or get_settings()
    store = store or LibraryStore(settings.library_dir)

    # Front-door routing (D-061): the orchestrator DECIDES per message which capability handles it,
    # BEFORE opening the catalog so a greeting never pays to load the vector matrix. Registry-driven
    # (any capability with a `route_when` is a choice) and biased to the library — a knowledge
    # question must never be answered from the model's memory (P6). Default-off knob.
    if settings.enable_router:
        from libkb.agent.roles.registry import get_registry
        from libkb.agent.roles.routes import RouteContext, decide_route, routes_from_registry

        registry = get_registry()
        routes = routes_from_registry(registry)
        if routes:
            route_id = decide_route(query, llm or get_llm(), settings, routes)
            # Any route with a `handle` gets the whole query; `search_library` (and any handle-less
            # route) falls through to the knowledge path below. A route may return None to DEFER to
            # the library — so a mis-route (e.g. the calculator on a non-math message) is caught.
            if route_id != "search_library" and registry.has(route_id):
                handle = getattr(registry.get(route_id), "handle", None)
                outcome = (
                    handle(
                        RouteContext(
                            query=query, store=store, llm=llm, settings=settings, emit=event_cb
                        )
                    )
                    if handle is not None
                    else None
                )
                if outcome is not None:
                    result = QueryResult(answer=outcome[0], nav=outcome[1])
                    _log_trajectory(query, result, settings)
                    return result

    owned_catalog = False
    if catalog is None and use_catalog:
        catalog = _open_catalog(settings)
        owned_catalog = catalog is not None
    if not use_catalog:
        catalog = None

    try:
        if shortcut and catalog is not None and catalog.count():
            result = _try_shortcut(query, store, catalog, llm, settings, event_cb)
            if result is not None:
                _log_trajectory(query, result, settings)
                return result

        # The cascade replaces the walk entirely: the embedder sieves, the LLM judges once.
        # It needs a catalog — without one there is nothing to sieve with, so fall back to the walk.
        if settings.retrieval_mode == "cascade" and catalog is not None and catalog.count():
            from libkb.agent.cascade import answer_by_cascade

            cascaded = answer_by_cascade(
                query,
                store=store,
                catalog=catalog,
                llm=llm,
                event_cb=event_cb,
                settings=settings,
            )
            result = QueryResult(answer=cascaded.answer, nav=cascaded.nav)
            _log_trajectory(query, result, settings)
            return result

        nav = navigate(query, store=store, llm=llm, catalog=catalog, event_cb=event_cb)
        if nav.status == "FOUND" and nav.pages:
            answer = compose_answer(query, nav.pages, store, llm=llm, settings=settings)
        else:
            answer = compose_not_found(query, nav.closest)
        result = QueryResult(answer=answer, nav=nav)
        _log_trajectory(query, result, settings)
        return result
    finally:
        if owned_catalog and catalog is not None:
            catalog.close()


def _log_trajectory(query: str, result: QueryResult, settings: Settings) -> None:
    """Remember what we were asked and where we went (§8.4).

    Best-effort by design: the demand-side flywheel is valuable, but not so valuable that a failure
    to write a log row may cost a reader their answer. Never raises.
    """
    if not settings.log_trajectories:
        return
    try:
        from libkb.trajectory.store import Trajectory, TrajectoryStore

        trajectories = TrajectoryStore(settings.db_path)
        try:
            trajectories.record(
                Trajectory(
                    query=query,
                    status=result.answer.status,
                    confidence=result.answer.confidence,
                    page_ids=[p.page_id for p in result.nav.pages],
                    path=result.answer.citations[0].path if result.answer.citations else "",
                    hops=result.nav.hops,
                    backtracks=result.nav.backtracks,
                    route=[
                        {"action": e.action, "title": e.title, "kind": e.kind, "node_id": e.node_id}
                        for e in result.nav.events
                    ],
                )
            )
        finally:
            trajectories.close()
    except Exception as exc:  # noqa: BLE001 — logging must never break answering
        log.warning("trajectory_log_failed", error=str(exc))


def answer_query_safe(
    query: str,
    *,
    store: LibraryStore | None = None,
    catalog: Catalog | None = None,
    llm: LLM | None = None,
    event_cb: EventCB | None = None,
    shortcut: bool = True,
    use_catalog: bool = True,
    settings: Settings | None = None,
) -> QueryResult:
    """Same as answer_query but converts ANY failure into an honest not-found.

    LLMError was the only expected failure and the only one caught — but a code bug raising a bare
    `TypeError` (a malformed model response slipping a `None` past a guard) would sail straight
    through and 500 a real user's request. P6 says a failure to answer is a NOT_FOUND, not a crash,
    so the net is cast wide: anything unexpected also fails CLOSED. It fails LOUD too — the full
    traceback is logged, so a masked bug stays a findable one (a truncated error string once hid
    exactly this)."""
    try:
        return answer_query(
            query,
            store=store,
            catalog=catalog,
            llm=llm,
            event_cb=event_cb,
            shortcut=shortcut,
            use_catalog=use_catalog,
            settings=settings,
        )
    except LLMError as exc:
        note = f"(The librarian couldn't reach the model: {exc})"
        return QueryResult(
            answer=compose_not_found(query, [], note=note),
            nav=NavResult(status="NOT_FOUND", reason=str(exc)),
        )
    except Exception as exc:  # noqa: BLE001 — an unexpected bug must fail closed (P6), never 500
        log.warning(
            "answer_query_crashed", query=query[:80], error=str(exc), tb=traceback.format_exc()
        )
        return QueryResult(
            answer=compose_not_found(query, [], note="(An unexpected error occurred.)"),
            nav=NavResult(status="NOT_FOUND", reason=str(exc)),
        )


def _try_shortcut(
    query: str,
    store: LibraryStore,
    catalog: Catalog,
    llm: LLM | None,
    settings: Settings,
    event_cb: EventCB | None,
) -> QueryResult | None:
    """Unambiguous catalog match → answer without walking. None ⇒ fall back to the walk.

    The gate is the MARGIN over the runner-up page, not an absolute cosine (D-028): scores crowd
    near 0.9, so an absolute gate fires on everything. With the margin gate the catalog stays
    quiet on questions it does not really recognise, and the walk handles those.
    """
    hits = lookup(
        catalog,
        query,
        llm=llm,
        top_k=settings.catalog_top_k,
        threshold=settings.catalog_shortcut_threshold,
        min_margin=settings.catalog_margin,
    )
    if not hits:
        return None
    pages = []
    for hit in hits:  # the margin gate leaves exactly the one page it is confident about
        try:
            pages.append(store.page(hit.page_id))
        except NodeNotFound:
            continue  # stale catalog row (page moved/removed) — skip it
    if not pages:
        return None

    answer = compose_answer(query, pages, store, llm=llm, settings=settings)
    if answer.status != "answered":
        return None  # answerer judged it insufficient → do the real walk

    events = [
        NavEvent(
            "lookup", "card catalog", None, None, "done", detail=f"{len(pages)} page(s) matched"
        ),
        NavEvent("found", "FOUND", None, None, "found", detail="card-catalog shortcut"),
    ]
    if event_cb:
        for ev in events:
            event_cb(ev)
    nav = NavResult(status="FOUND", pages=pages, reason="card-catalog shortcut", events=events)
    return QueryResult(answer=answer, nav=nav)


def _open_catalog(settings: Settings) -> Catalog | None:
    """Open the on-disk catalog if it exists — never create one as a query side effect."""
    if not settings.db_path.exists():
        return None
    try:
        return Catalog(settings.db_path)
    except Exception:  # a missing/corrupt catalog must not break querying
        return None
