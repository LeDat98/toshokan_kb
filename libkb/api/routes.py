"""HTTP routes. The library store is created once in app.state (see main.py)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
from pathlib import Path

import structlog
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from libkb.agent.orchestrator import answer_query_safe
from libkb.api.events import (
    AnswerPayload,
    ImportReportModel,
    IngestOutcomeModel,
    IngestStepEvent,
    NodeModel,
    PageModel,
    StepEvent,
    sse,
)
from libkb.catalog.store import Catalog
from libkb.config import get_settings
from libkb.exceptions import NodeNotFound
from libkb.library.models import ROOT_ID, one_line_of
from libkb.library.store import LibraryStore

router = APIRouter()
log = structlog.get_logger(__name__)


class QueryBody(BaseModel):
    q: str
    # Every option below is a property of the QUERY, not the process — the UI's panel sends them and
    # they ride with this one request (like `model` already does). None ⇒ use the server default.
    model: str | None = None
    depth: str | None = None  # auto | minimum | default | deep  (retrieval window, D-058)
    basket: str | None = None  # auto | 10 | 20                   (pages opened, D-058)
    ban_invented: bool | None = None  # anti-fabrication gate (D-057)
    # the conversation to continue (chat history). None/unknown ⇒ start a fresh one; the id the
    # backend used comes back on the answer so the next turn threads onto it.
    conversation_id: str | None = None


_DEPTH_OPTS = ("auto", "minimum", "default", "deep")
_BASKET_OPTS = ("auto", "10", "20")


def _request_settings(settings, body: QueryBody):
    """A per-request Settings from the option panel — validated against the fixed menus so a bad
    value from the wire can never widen the window or flip a gate to something unmeasured."""
    overrides: dict = {}
    if body.depth in _DEPTH_OPTS:
        overrides["cascade_depth"] = body.depth
    if body.basket in _BASKET_OPTS:
        overrides["cascade_basket"] = body.basket
    if body.ban_invented is not None:
        overrides["answer_ban_invented_specifics"] = bool(body.ban_invented)
    return settings.model_copy(update=overrides) if overrides else settings


# Approximate USD per 1M tokens (input, output) — for the details panel's cost estimate ONLY, not
# billing. Unknown models fall back to zero rather than a wrong guess.
_PRICES = {
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "qwen-plus": (0.40, 0.80),
    "qwen-flash": (0.15, 0.40),
    "qwen3-max": (1.60, 6.40),
    "global.anthropic.claude-haiku-4-5-20251001-v1:0": (1.00, 5.00),
}


def _answer_meta(settings, chosen: str | None, llm, tok0: tuple[int, int], t0: float) -> dict:
    """Per-query details for the UI. Tokens are the generation delta on this request's client (a
    with_model clone zeroes its counters, so a NON-default model is exact; the shared default can
    interleave with concurrent requests — an estimate, and labelled as one)."""
    model = chosen or settings.model
    din = max(llm.total_input_tokens - tok0[0], 0)
    dout = max(llm.total_output_tokens - tok0[1], 0)
    pin, pout = _PRICES.get(model, (0.0, 0.0))
    return {
        "model": model,
        "depth": settings.cascade_depth,
        "basket": settings.cascade_basket,
        "input_tokens": din,
        "output_tokens": dout,
        "cost_usd": round(din / 1e6 * pin + dout / 1e6 * pout, 6),
        "latency_ms": int((time.monotonic() - t0) * 1000),
    }


class ImportBody(BaseModel):
    folder_path: str
    domain: str
    shelves: str = "single"
    shelf_name: str = "General"
    index: bool = False  # also build catalog entries (P2c) — spends tokens per page


class ApproveBody(BaseModel):
    domain: str
    shelf: str


def _store(request: Request) -> LibraryStore:
    return request.app.state.store


def _has_library(store: LibraryStore) -> bool:
    try:
        store.get(ROOT_ID)
        return True
    except NodeNotFound:
        return False


@router.get("/health")
def health(request: Request) -> dict:
    store = _store(request)
    settings = get_settings()
    seeded = _has_library(store)
    stats = store.get(ROOT_ID).stats if seeded else None
    return {
        "ok": True,
        "model": settings.model,
        "seeded": seeded,
        "library": (
            {"shelves": stats.n_shelves, "books": stats.n_books, "pages": stats.n_pages}
            if stats
            else None
        ),
    }


@router.get("/models")
def models() -> dict:
    """The picker's menu. `tools` is the honest part: a Qwen model cannot run the tree-WALK (tool
    calling is Gemini-only, llm/client.py), so the UI must grey it out *before* the user picks it
    rather than let a walk die halfway through. The cascade — the default — is tool-free, so every
    model here can run it."""
    from libkb.llm.client import get_llm

    settings = get_settings()
    llm = get_llm()
    rows = []
    for name in settings.selectable_models:
        dashscope = not llm.supports_tools(name)
        rows.append(
            {
                "name": name,
                "provider": "dashscope" if dashscope else "gemini",
                "tools": not dashscope,
                # a model whose provider has no key configured must not be offered as if it worked
                "available": bool(settings.dashscope_api_key) if dashscope else True,
            }
        )
    return {
        "models": rows,
        "current": settings.model,
        "retrieval_mode": settings.retrieval_mode,
    }


@router.get("/persona")
def persona() -> dict:
    """The librarian's behaviour/persona, verbatim (D-059) — so the UI can SHOW how it is defined to
    behave, read-only. One file is the single source; this just serves it."""
    path = Path(__file__).parent.parent / "llm" / "prompts" / "persona.md"
    try:
        return {"text": path.read_text(encoding="utf-8")}
    except OSError:
        return {"text": ""}


@router.get("/options")
def options(request: Request) -> dict:
    """The retrieval/answer dials the UI panel exposes, with the current defaults AND — for the
    'auto' tiers — what they RESOLVE to for this corpus right now (D-058), so the panel can show
    'auto → window 20 / basket 10 (113-page library)' instead of an opaque word."""
    settings = get_settings()
    n_pages = 0
    if settings.db_path.exists():
        try:
            cat = Catalog(settings.db_path)
            n_pages = len(cat.page_ids())
            cat.close()
        except Exception:  # a missing/corrupt catalog must not break the panel
            n_pages = 0
    fetch_n, _k, basket = settings.resolve_cascade(n_pages)
    return {
        "depth": {"options": list(_DEPTH_OPTS), "current": settings.cascade_depth},
        "basket": {"options": list(_BASKET_OPTS), "current": settings.cascade_basket},
        "ban_invented": settings.answer_ban_invented_specifics,
        "corpus_pages": n_pages,
        "resolved": {"fetch": fetch_n, "basket": basket},
    }


# ── Observatory: the learning loop, from real logged traffic ─────────────────────────────────────
# KPIs and the trajectories feed are computed from the TrajectoryStore — every answered/declined
# query is logged there (log_trajectories, default on). The eval-history chart, misroute heatmap and
# suggested-fixes are DELIBERATELY not served here: they need `trajectory/analyzer.py`, which is not
# built yet. The UI shows those as a labelled preview rather than fabricating measured numbers.

_NODE_KINDS = {"domain", "shelf", "book", "page"}
_REASON_TYPE = {  # everything else → "Lookup"
    "synthesize": "Synthesis",
    "decompose": "Synthesis",
    "walk": "Explore",
}


def _traj_replay(route: list[dict]) -> list[dict]:
    """The node-touching steps of a trajectory, for the read-only trace replay. Process-only events
    (lookup/read/compose/thought) carry no node kind and are skipped — a cascade shows its basket
    pages, a walk shows the path it walked, a synthesis shows nothing to walk (honest)."""
    steps: list[dict] = []
    for ev in route:
        kind = ev.get("kind")
        if kind not in _NODE_KINDS:
            continue
        action = ev.get("action", "")
        if action == "back":
            state = "back"
        elif action in ("read", "found", "triage"):
            state = "read"
        else:
            state = "done"
        steps.append({"kind": kind, "title": ev.get("title", ""), "state": state})
    return steps


def _bucket(items: list, metric, n: int = 8) -> list[float]:
    """Split a chronological list into up to `n` contiguous buckets and return `metric` per bucket —
    a REAL rolling trend for a sparkline, never a synthetic one. Empty below two points."""
    if len(items) < 2:
        return []
    n = min(n, len(items))
    size = len(items) / n
    out: list[float] = []
    for i in range(n):
        lo, hi = int(i * size), (int((i + 1) * size) if i < n - 1 else len(items))
        chunk = items[lo:hi]
        if chunk:
            out.append(round(metric(chunk), 2))
    return out


def _observatory(*, table_limit: int = 40, window: int = 200) -> dict:
    """KPIs + the trajectories feed, from the logged query traffic. `available=False` when there is
    no catalog db or no traffic yet — the UI then shows an honest empty state, not zeros."""
    settings = get_settings()
    if not settings.db_path.exists():
        return {"available": False, "kpis": [], "trajectories": []}
    from libkb.trajectory.store import TrajectoryStore

    store = TrajectoryStore(settings.db_path)
    try:
        counts = store.status_counts()
        recent = store.recent(limit=window)  # newest first
    finally:
        store.close()
    total = sum(counts.values())
    if total == 0:
        return {"available": False, "kpis": [], "trajectories": []}

    answered = counts.get("answered", 0)
    not_found = total - answered
    chron = list(reversed(recent))  # oldest → newest, for the trend
    ans_spark = _bucket(chron, lambda c: 100.0 * sum(t.status == "answered" for t in c) / len(c))
    answered_only = [t for t in chron if t.status == "answered"]
    hop_spark = _bucket(answered_only, lambda c: sum(t.hops for t in c) / len(c))
    avg_hops = (sum(t.hops for t in answered_only) / len(answered_only)) if answered_only else 0.0

    def _delta(spark: list[float], unit: str, higher_is_good: bool) -> tuple[str, bool]:
        if len(spark) < 2:
            return "", True
        d = spark[-1] - spark[0]
        arrow = "▲" if d >= 0 else "▼"
        good = (d >= 0) if higher_is_good else (d <= 0)
        return f"{arrow} {abs(d):.1f}{unit}", good

    ans_delta, ans_good = _delta(ans_spark, " pts", higher_is_good=True)
    hop_delta, hop_good = _delta(hop_spark, "", higher_is_good=False)
    kpis = [
        {"label": "Queries logged", "value": str(total), "delta": "", "good": True, "spark": []},
        {
            "label": "Answer rate",
            "value": f"{100 * answered / total:.0f}%",
            "delta": ans_delta,
            "good": ans_good,
            "spark": ans_spark,
        },
        {
            "label": "Honest NOT_FOUND",
            "value": f"{100 * not_found / total:.0f}%",
            "delta": "",
            "good": True,
            "spark": [],
        },
        {
            "label": "Avg hops",
            "value": f"{avg_hops:.1f}",
            "delta": hop_delta,
            "good": hop_good,
            "spark": hop_spark,
        },
    ]

    trajectories = [
        {
            "id": f"t{t.id}",
            "time": t.created_at[11:16] if len(t.created_at) >= 16 else "",
            "query": t.query,
            "type": _REASON_TYPE.get(t.reason, "Lookup"),
            "hops": t.hops,
            "back": t.backtracks,
            "outcome": "FOUND" if t.status == "answered" else "NOT_FOUND",
            "dur": "",  # per-query latency is not stored on the trajectory (honest blank)
            "replay": _traj_replay(t.route),
        }
        for t in recent[:table_limit]
    ]
    return {"available": True, "kpis": kpis, "trajectories": trajectories}


@router.get("/observatory")
def observatory() -> dict:
    """Real KPIs + the trajectories feed for the Observatory screen (learning-loop panels stay a
    labelled preview until `trajectory/analyzer.py` exists)."""
    return _observatory()


# ── Conversations: chat history + multi-turn context ─────────────────────────────────────────────
# The transcript store lives in the same db as the catalog (gitignored — it holds real user text).
# The /query endpoint threads history through it; these endpoints list/read/delete for the UI.


def _open_conversation(settings, conversation_id: str | None, first_query: str):
    """Resolve-or-create the conversation and load its PRIOR turns for the contextualizer.

    Best-effort: on any store error, returns (None, id-or-'', []) so the turn still answers,
    statelessly — chat memory is valuable, but never more valuable than the answer itself."""
    from libkb.conversation.store import ConversationStore

    try:
        conv = ConversationStore(settings.db_path)
    except Exception as exc:  # noqa: BLE001 — degrade to a stateless turn, never 500
        log.warning("conversation_open_failed", error=str(exc))
        return None, (conversation_id or ""), []
    try:
        if conversation_id and conv.exists(conversation_id):
            cid = conversation_id
        else:
            cid = conv.create(title=first_query.strip())
        history = [
            {"role": m.role, "text": m.text}
            for m in conv.history(cid, limit=settings.context_history_turns)
        ]
        return conv, cid, history
    except Exception as exc:  # noqa: BLE001
        log.warning("conversation_load_failed", error=str(exc))
        conv.close()
        return None, (conversation_id or ""), []


def _save_turn(conv, cid: str, query: str, result) -> None:
    """Persist the user turn and the assistant's answer. Best-effort; never fatal to a response."""
    if conv is None:
        return
    try:
        conv.append(cid, "user", query)
        conv.append(
            cid,
            "assistant",
            result.answer.text,
            status=result.answer.status,
            confidence=result.answer.confidence,
            reason=result.nav.reason,
            citations=[{"path": c.path, "page_id": c.page_id} for c in result.answer.citations],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("conversation_save_failed", cid=cid, error=str(exc))
    finally:
        conv.close()


@router.get("/conversations")
def conversations_list() -> dict:
    """Recent conversations (id, title, when, message count) — newest first, for a history list."""
    settings = get_settings()
    if not settings.db_path.exists():
        return {"conversations": []}
    from libkb.conversation.store import ConversationStore

    conv = ConversationStore(settings.db_path)
    try:
        rows = conv.list()
    finally:
        conv.close()
    return {
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "pinned": c.pinned,
                "n_messages": c.n_messages,
            }
            for c in rows
        ]
    }


@router.get("/conversations/{cid}")
def conversation_get(cid: str) -> dict:
    """The full transcript of one conversation, so the UI can resume it."""
    settings = get_settings()
    from libkb.conversation.store import ConversationStore

    if not settings.db_path.exists():
        raise HTTPException(status_code=404, detail="conversation not found")
    conv = ConversationStore(settings.db_path)
    try:
        out = conv.transcript(cid)
    finally:
        conv.close()
    if out is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    meta, msgs = out
    return {
        "id": meta.id,
        "title": meta.title,
        "created_at": meta.created_at,
        "updated_at": meta.updated_at,
        "pinned": meta.pinned,
        "messages": [
            {
                "role": m.role,
                "text": m.text,
                "status": m.status,
                "confidence": m.confidence,
                "reason": m.reason,
                "citations": m.citations,
                "created_at": m.created_at,
            }
            for m in msgs
        ],
    }


class RenameBody(BaseModel):
    title: str


class PinBody(BaseModel):
    pinned: bool


@router.patch("/conversations/{cid}")
def conversation_rename(cid: str, body: RenameBody) -> dict:
    """Rename a conversation (the history sidebar's inline edit). Empty title is refused."""
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be empty")
    settings = get_settings()
    if not settings.db_path.exists():
        raise HTTPException(status_code=404, detail="conversation not found")
    from libkb.conversation.store import ConversationStore

    conv = ConversationStore(settings.db_path)
    try:
        ok = conv.rename(cid, title)
    finally:
        conv.close()
    if not ok:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"id": cid, "title": title[:120]}


@router.post("/conversations/{cid}/pin")
def conversation_pin(cid: str, body: PinBody) -> dict:
    """Pin/unpin a conversation to the top of the history list. Pinning is capped (MAX_PINNED); over
    the cap, `at_limit` comes back true and nothing changes — the UI tells the user."""
    settings = get_settings()
    if not settings.db_path.exists():
        raise HTTPException(status_code=404, detail="conversation not found")
    from libkb.conversation.store import MAX_PINNED, ConversationStore

    conv = ConversationStore(settings.db_path)
    try:
        outcome = conv.set_pinned(cid, body.pinned)
    finally:
        conv.close()
    if outcome == "missing":
        raise HTTPException(status_code=404, detail="conversation not found")
    return {
        "id": cid,
        "pinned": outcome == "pinned",
        "at_limit": outcome == "limit",
        "max_pinned": MAX_PINNED,
    }


@router.delete("/conversations/{cid}")
def conversation_delete(cid: str) -> dict:
    settings = get_settings()
    if not settings.db_path.exists():
        return {"deleted": False}
    from libkb.conversation.store import ConversationStore

    conv = ConversationStore(settings.db_path)
    try:
        ok = conv.delete(cid)
    finally:
        conv.close()
    return {"deleted": ok}


# ── Semantic answer cache: view, edit (curate), toggle, delete ───────────────────────────────────


class CacheToggleBody(BaseModel):
    enabled: bool


class CacheEditBody(BaseModel):
    answer: str | None = None
    enabled: bool | None = None


def _entry_dict(e) -> dict:
    return {
        "id": e.id,
        "query": e.query,
        "answer": e.answer,
        "confidence": e.confidence,
        "citations": e.citations,
        "curated": e.curated,
        "enabled": e.enabled,
        "hits": e.hits,
        "created_at": e.created_at,
        "last_hit_at": e.last_hit_at,
    }


@router.get("/cache")
def cache_list() -> dict:
    """The cached answers for the Observatory panel, plus the effective on/off state. `enabled` is
    env AND the runtime toggle — the env knob is a hard master, the toggle is what the UI flips."""
    settings = get_settings()
    if not settings.db_path.exists():
        return {"enabled": settings.enable_answer_cache, "entries": []}
    from libkb.cache.store import AnswerCache

    cache = AnswerCache(settings.db_path)
    try:
        enabled = settings.enable_answer_cache and cache.is_enabled()
        entries = [_entry_dict(e) for e in cache.list()]
    finally:
        cache.close()
    return {"enabled": enabled, "entries": entries}


@router.post("/cache/toggle")
def cache_toggle(body: CacheToggleBody) -> dict:
    """Global on/off for the cache (persisted). When off, every question runs the full pipeline."""
    settings = get_settings()
    if not settings.db_path.exists():
        raise HTTPException(status_code=404, detail="no cache yet")
    from libkb.cache.store import AnswerCache

    cache = AnswerCache(settings.db_path)
    try:
        cache.set_enabled(body.enabled)
        enabled = settings.enable_answer_cache and cache.is_enabled()
    finally:
        cache.close()
    return {"enabled": enabled}


@router.patch("/cache/{entry_id}")
def cache_edit(entry_id: int, body: CacheEditBody) -> dict:
    """Edit a cached answer (marks it curated → sticky) and/or enable/disable a single entry."""
    settings = get_settings()
    if not settings.db_path.exists():
        raise HTTPException(status_code=404, detail="not found")
    from libkb.cache.store import AnswerCache

    cache = AnswerCache(settings.db_path)
    try:
        if body.answer is not None:
            text = body.answer.strip()
            if not text:
                raise HTTPException(status_code=400, detail="answer must not be empty")
            cache.update_answer(entry_id, text)
        if body.enabled is not None:
            cache.set_entry_enabled(entry_id, body.enabled)
        entry = cache.get(entry_id)
    finally:
        cache.close()
    if entry is None:
        raise HTTPException(status_code=404, detail="not found")
    return _entry_dict(entry)


@router.delete("/cache/{entry_id}")
def cache_delete(entry_id: int) -> dict:
    settings = get_settings()
    if not settings.db_path.exists():
        return {"deleted": False}
    from libkb.cache.store import AnswerCache

    cache = AnswerCache(settings.db_path)
    try:
        ok = cache.delete(entry_id)
    finally:
        cache.close()
    return {"deleted": ok}


@router.get("/agents")
def agents() -> dict:
    """The registered agent roles and their A2A-shaped cards (D-061, Phase B) — discovery for the
    orchestration layer and, later, external A2A/MCP peers. A new agent shows up here for free."""
    from dataclasses import asdict

    from libkb.agent.roles.registry import get_registry

    return {"agents": [asdict(c) for c in get_registry().cards()]}


@router.get("/a2a/agent-card")
def a2a_agent_card() -> dict:
    """This system AS an A2A-discoverable agent (Phase C, D-061). External A2A peers read this card
    to learn who we are and what skills we expose; each registered agent becomes an A2A skill."""
    from libkb.agent.roles.registry import get_registry

    skills = [
        {"id": c.id, "name": c.name, "description": c.description, "tags": c.skills}
        for c in get_registry().cards()
    ]
    return {
        "name": "LibraryKB",
        "description": "A library-style knowledge base that walks domain -> shelf -> book -> page "
        "to answer, cites the path it walked, and returns an honest NOT_FOUND when nothing fits.",
        "version": "0.1.0",
        "url": "/api",
        "capabilities": {"streaming": True},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": skills,
    }


@router.post("/query")
async def query(body: QueryBody, request: Request) -> StreamingResponse:
    from libkb.llm.client import get_llm

    store = _store(request)
    q = body.q.strip()
    settings = get_settings()
    req_settings = _request_settings(settings, body)  # depth/basket/gates ride with this request
    chosen = (body.model or "").strip() or None
    llm = get_llm().with_model(chosen)

    # Refuse before spending, not after: the walk needs tools, and no DashScope model has them.
    blocked = (
        chosen
        and not llm.supports_tools()
        and settings.retrieval_mode != "cascade"
        and f"{chosen} cannot run the tree-walk (tool calling is Gemini-only). "
        "Switch LIBKB_RETRIEVAL_MODE to cascade, or pick a Gemini model."
    )

    async def stream():
        if not q:
            yield sse("error", {"message": "empty query"})
            yield sse("done", {})
            return
        if blocked:
            yield sse("error", {"message": blocked})
            yield sse("done", {})
            return
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def emit(ev) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, ("nav", ev))

        def run() -> None:
            try:
                # Load the conversation (chat history) — best-effort: a persistence failure must not
                # cost the reader an answer, so a broken store degrades to a stateless turn.
                conv, cid, history = _open_conversation(settings, body.conversation_id, q)

                t0 = time.monotonic()
                tok0 = (llm.total_input_tokens, llm.total_output_tokens)
                result = answer_query_safe(
                    q, store=store, llm=llm, event_cb=emit, settings=req_settings, history=history
                )
                meta = _answer_meta(req_settings, chosen, llm, tok0, t0)
                meta["conversation_id"] = cid
                _save_turn(conv, cid, q, result)  # persist the user turn + the assistant's answer
                loop.call_soon_threadsafe(queue.put_nowait, ("answer", (result, meta)))
            except Exception as exc:  # noqa: BLE001 - surfaced to the client as an error event
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

        threading.Thread(target=run, daemon=True).start()

        while True:
            kind, payload = await queue.get()
            if kind == "nav":
                yield sse("nav", StepEvent.of(payload))
            elif kind == "answer":
                result, meta = payload
                yield sse("answer", AnswerPayload.of(result.answer, result.nav, meta))
            elif kind == "error":
                yield sse("error", {"message": payload})
            elif kind == "done":
                yield sse("done", {})
                break

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/library/tree")
def library_tree(request: Request, depth: int = 3) -> dict:
    store = _store(request)
    if not _has_library(store):
        return {"id": ROOT_ID, "kind": "root", "title": "Library", "children": []}

    def build(node_id: str, remaining: int) -> dict:
        meta = store.get(node_id)
        node = {
            "id": meta.id,
            "kind": meta.kind,
            "title": meta.title,
            "one_line": one_line_of(meta.description),
            "children": [],
        }
        if remaining <= 0 or meta.kind == "book":
            return node
        for card in store.children(node_id):
            if card.kind == "page":
                continue
            node["children"].append(build(card.id, remaining - 1))
        return node

    return build(ROOT_ID, depth)


@router.get("/library/node/{node_id}")
def library_node(node_id: str, request: Request) -> NodeModel:
    store = _store(request)
    try:
        meta = store.get(node_id)
        children = [] if meta.kind == "page" else store.children(node_id)
        return NodeModel.of(meta, children, store.path_of(node_id))
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/library/book/{book_id}")
def library_book(book_id: str, request: Request) -> dict:
    store = _store(request)
    try:
        meta = store.get(book_id)
        toc = store.toc(book_id)
        return {
            "id": meta.id,
            "title": meta.title,
            "description": meta.description,
            "breadcrumb": [r.model_dump() for r in _refs(store, book_id)],
            "chapters": [
                {
                    "title": ch.title,
                    "entries": [
                        {
                            "page_id": e.page_id,
                            "title": e.title,
                            # a TOC line is a spine label; the stored value may be an essay (§0a)
                            "one_line": one_line_of(e.one_line, get_settings().max_one_line_chars),
                            "keywords": e.keywords,
                        }
                        for e in ch.entries
                    ],
                }
                for ch in toc.chapters
            ],
        }
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/library/page/{page_id}")
def library_page(page_id: str, request: Request) -> PageModel:
    store = _store(request)
    try:
        page = store.page(page_id)
        return PageModel.of(page, store.path_of(page_id))
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/import")
async def import_route(body: ImportBody, request: Request) -> StreamingResponse:
    store = _store(request)

    async def stream():
        if not Path(body.folder_path).is_dir():
            yield sse("error", {"message": f"not a folder: {body.folder_path}"})
            yield sse("done", {})
            return
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def run() -> None:
            catalog = None
            try:
                from libkb.ingest.importer import import_folder
                from libkb.llm.client import get_llm

                llm = get_llm() if (body.shelves == "auto" or body.index) else None
                if body.index:
                    catalog = Catalog(get_settings().db_path)
                report = import_folder(
                    body.folder_path,
                    body.domain,
                    store,
                    strategy=body.shelves,
                    shelf_name=body.shelf_name,
                    llm=llm,
                    catalog=catalog,
                    progress=lambda m: loop.call_soon_threadsafe(queue.put_nowait, ("log", m)),
                )
                loop.call_soon_threadsafe(queue.put_nowait, ("report", report))
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))
            finally:
                if catalog is not None:
                    catalog.close()
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

        threading.Thread(target=run, daemon=True).start()
        while True:
            kind, payload = await queue.get()
            if kind == "log":
                yield sse("log", {"message": payload})
            elif kind == "report":
                yield sse("report", ImportReportModel.of(payload))
            elif kind == "error":
                yield sse("error", {"message": payload})
            elif kind == "done":
                yield sse("done", {})
                break

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/ingest")
async def ingest_route(
    request: Request,
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
    text: str | None = Form(None),
) -> StreamingResponse:
    store = _store(request)
    tmp_path: str | None = None
    source: str | None = None
    if file is not None:
        data = await file.read()
        suffix = Path(file.filename or "upload").suffix or ".txt"
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        source = tmp_path
    elif url and url.strip():
        source = url.strip()
    elif text and text.strip():
        fd, tmp_path = tempfile.mkstemp(suffix=".md")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        source = tmp_path

    async def stream():
        if not source:
            yield sse("error", {"message": "provide a file, url, or text"})
            yield sse("done", {})
            return
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def run() -> None:
            catalog = None
            try:
                from libkb.ingest.pipeline import ingest_document

                catalog = Catalog(get_settings().db_path)  # index filed pages into the flywheel
                outcome = ingest_document(
                    source,
                    store,
                    catalog=catalog,
                    event_cb=lambda ev: loop.call_soon_threadsafe(queue.put_nowait, ("step", ev)),
                )
                loop.call_soon_threadsafe(queue.put_nowait, ("outcome", outcome))
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))
            finally:
                if catalog is not None:
                    catalog.close()
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

        threading.Thread(target=run, daemon=True).start()
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "step":
                    yield sse(
                        "step",
                        IngestStepEvent(
                            stage=payload.stage, status=payload.status, detail=payload.detail
                        ),
                    )
                elif kind == "outcome":
                    yield sse("outcome", IngestOutcomeModel.of(payload))
                elif kind == "error":
                    yield sse("error", {"message": payload})
                elif kind == "done":
                    yield sse("done", {})
                    break
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/ingest/review")
def ingest_review(request: Request) -> dict:
    from libkb.ingest.pipeline import list_uncatalogued

    return {"rows": list_uncatalogued(_store(request))}


@router.post("/ingest/review/{book_id}/approve")
def ingest_approve(book_id: str, body: ApproveBody, request: Request) -> dict:
    from libkb.ingest.pipeline import approve_placement
    from libkb.llm.client import get_llm

    catalog = Catalog(get_settings().db_path)  # index the now-approved pages into the flywheel
    try:
        path = approve_placement(
            _store(request), book_id, body.domain, body.shelf, catalog=catalog, llm=get_llm()
        )
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        catalog.close()
    return {"path": path}


def _refs(store: LibraryStore, node_id: str):
    from libkb.api.events import RefModel

    return [RefModel.of(r) for r in store.path_of(node_id)]
