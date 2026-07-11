"""HTTP routes. The library store is created once in app.state (see main.py)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from libkb.agent.orchestrator import answer_query_safe
from libkb.api.events import (
    AnswerPayload,
    CardModel,
    ImportReportModel,
    IngestOutcomeModel,
    IngestStepEvent,
    NodeModel,
    PageModel,
    StepEvent,
    sse,
)
from libkb.config import get_settings
from libkb.exceptions import NodeNotFound
from libkb.library.models import ROOT_ID, one_line_of
from libkb.library.store import LibraryStore

router = APIRouter()


class QueryBody(BaseModel):
    q: str


class ImportBody(BaseModel):
    folder_path: str
    domain: str
    shelves: str = "single"
    shelf_name: str = "General"


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


@router.post("/query")
async def query(body: QueryBody, request: Request) -> StreamingResponse:
    store = _store(request)
    q = body.q.strip()

    async def stream():
        if not q:
            yield sse("error", {"message": "empty query"})
            yield sse("done", {})
            return
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def emit(ev) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, ("nav", ev))

        def run() -> None:
            try:
                result = answer_query_safe(q, store=store, event_cb=emit)
                loop.call_soon_threadsafe(queue.put_nowait, ("answer", result))
            except Exception as exc:  # noqa: BLE001 - surfaced to the client as an error event
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

        threading.Thread(target=run, daemon=True).start()

        while True:
            kind, payload = await queue.get()
            if kind == "nav":
                yield sse("nav", StepEvent.of(payload))
            elif kind == "answer":
                yield sse("answer", AnswerPayload.of(payload.answer, payload.nav))
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
                            "one_line": e.one_line,
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
            try:
                from libkb.ingest.importer import import_folder
                from libkb.llm.client import get_llm

                llm = get_llm() if body.shelves == "auto" else None
                report = import_folder(
                    body.folder_path,
                    body.domain,
                    store,
                    strategy=body.shelves,
                    shelf_name=body.shelf_name,
                    llm=llm,
                    progress=lambda m: loop.call_soon_threadsafe(queue.put_nowait, ("log", m)),
                )
                loop.call_soon_threadsafe(queue.put_nowait, ("report", report))
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))
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
            try:
                from libkb.ingest.pipeline import ingest_document

                outcome = ingest_document(
                    source,
                    store,
                    event_cb=lambda ev: loop.call_soon_threadsafe(
                        queue.put_nowait, ("step", ev)
                    ),
                )
                loop.call_soon_threadsafe(queue.put_nowait, ("outcome", outcome))
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))
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

    try:
        path = approve_placement(_store(request), book_id, body.domain, body.shelf)
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"path": path}


def _refs(store: LibraryStore, node_id: str):
    from libkb.api.events import RefModel

    return [RefModel.of(r) for r in store.path_of(node_id)]


def _cards(cards) -> list[CardModel]:
    return [CardModel.of(c) for c in cards]
