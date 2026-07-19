"""HTTP routes. The library store is created once in app.state (see main.py)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
from pathlib import Path

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


class QueryBody(BaseModel):
    q: str
    # Every option below is a property of the QUERY, not the process — the UI's panel sends them and
    # they ride with this one request (like `model` already does). None ⇒ use the server default.
    model: str | None = None
    depth: str | None = None  # auto | minimum | default | deep  (retrieval window, D-058)
    basket: str | None = None  # auto | 10 | 20                   (pages opened, D-058)
    ban_invented: bool | None = None  # anti-fabrication gate (D-057)


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
                t0 = time.monotonic()
                tok0 = (llm.total_input_tokens, llm.total_output_tokens)
                result = answer_query_safe(
                    q, store=store, llm=llm, event_cb=emit, settings=req_settings
                )
                meta = _answer_meta(req_settings, chosen, llm, tok0, t0)
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
