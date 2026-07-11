"""The SSE / JSON contract shared with the web UI (web/src/api.ts).

Event names are versioned here; keep them in sync with the frontend on both sides.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from libkb.agent.answerer import Answer
from libkb.agent.navigator import NavResult
from libkb.agent.tools import NavEvent
from libkb.library.models import NodeCard, NodeMeta, NodeRef, PageContent


class StepEvent(BaseModel):
    action: str  # enter | open | read | back | found | not_found | budget
    title: str
    kind: str | None = None
    node_id: str | None = None
    status: str = "done"
    detail: str = ""
    snippet: str = ""

    @classmethod
    def of(cls, ev: NavEvent) -> StepEvent:
        return cls(
            action=ev.action,
            title=ev.title,
            kind=ev.kind,
            node_id=ev.node_id,
            status=ev.status,
            detail=ev.detail,
            snippet=ev.snippet,
        )


class CitationModel(BaseModel):
    path: str
    page_id: str


class AnswerPayload(BaseModel):
    text: str
    status: str  # answered | not_found
    confidence: str
    citations: list[CitationModel]
    closest: list[str] = []
    hops: int = 0
    backtracks: int = 0

    @classmethod
    def of(cls, answer: Answer, nav: NavResult) -> AnswerPayload:
        return cls(
            text=answer.text,
            status=answer.status,
            confidence=answer.confidence,
            citations=[CitationModel(path=c.path, page_id=c.page_id) for c in answer.citations],
            closest=nav.closest,
            hops=nav.hops,
            backtracks=nav.backtracks,
        )


class RefModel(BaseModel):
    id: str
    kind: str
    title: str
    slug: str

    @classmethod
    def of(cls, ref: NodeRef) -> RefModel:
        return cls(id=ref.id, kind=ref.kind, title=ref.title, slug=ref.slug)


class CardModel(BaseModel):
    id: str
    kind: str
    title: str
    one_line: str = ""
    stats_line: str = ""
    see_also: list[str] = []

    @classmethod
    def of(cls, card: NodeCard) -> CardModel:
        return cls(
            id=card.id,
            kind=card.kind,
            title=card.title,
            one_line=card.one_line,
            stats_line=card.stats_line,
            see_also=card.see_also,
        )


class NodeModel(BaseModel):
    id: str
    kind: str
    title: str
    description: str = ""
    breadcrumb: list[RefModel] = []
    children: list[CardModel] = []
    see_also: list[str] = []

    @classmethod
    def of(cls, meta: NodeMeta, children: list[NodeCard], breadcrumb: list[NodeRef]) -> NodeModel:
        return cls(
            id=meta.id,
            kind=meta.kind,
            title=meta.title,
            description=meta.description,
            breadcrumb=[RefModel.of(r) for r in breadcrumb],
            children=[CardModel.of(c) for c in children],
            see_also=[f"{sa.note} — see: {sa.target.title}" for sa in meta.see_also],
        )


class PageModel(BaseModel):
    page_id: str
    book_id: str
    title: str
    markdown: str
    source_ref: str | None = None
    breadcrumb: list[RefModel] = []

    @classmethod
    def of(cls, page: PageContent, breadcrumb: list[NodeRef]) -> PageModel:
        return cls(
            page_id=page.page_id,
            book_id=page.book_id,
            title=page.title,
            markdown=page.markdown,
            source_ref=page.source_ref,
            breadcrumb=[RefModel.of(r) for r in breadcrumb],
        )


class IngestStepEvent(BaseModel):
    stage: str  # parse | split | classify | file
    status: str  # running | done | gated | failed
    detail: str = ""


class IngestOutcomeModel(BaseModel):
    status: str  # filed | uncatalogued
    book_id: str
    book_path: str
    n_pages: int
    gated: bool
    confidence: float
    proposed_path: str
    rationale: str
    source_type: str = ""

    @classmethod
    def of(cls, outcome) -> IngestOutcomeModel:
        p = outcome.placement
        return cls(
            status=outcome.status,
            book_id=outcome.book_id,
            book_path=outcome.book_path,
            n_pages=outcome.n_pages,
            gated=outcome.gated,
            confidence=p.confidence,
            proposed_path=p.path,
            rationale=p.rationale,
            source_type=outcome.source_type,
        )


class ReviewRow(BaseModel):
    id: str
    title: str
    n_pages: int
    proposed_domain: str
    proposed_shelf: str
    confidence: float | None
    rationale: str


class ImportReportModel(BaseModel):
    domain: str
    shelves: int
    books: int
    pages: int
    skipped_pages: int
    provided: list[str]
    missing: list[str]
    paths: list[str]

    @classmethod
    def of(cls, report) -> ImportReportModel:
        return cls(
            domain=report.domain,
            shelves=report.shelves,
            books=report.books,
            pages=report.pages,
            skipped_pages=report.skipped_pages,
            provided=report.provided,
            missing=report.missing,
            paths=report.paths,
        )


def sse(event: str, data: BaseModel | dict) -> str:
    payload = data.model_dump() if isinstance(data, BaseModel) else data
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
