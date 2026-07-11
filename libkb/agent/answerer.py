"""Evidence pages → a cited answer, or an honest NOT_FOUND (principle P6)."""

from __future__ import annotations

from dataclasses import dataclass, field

from libkb.library.models import NodeRef, PageContent
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "sufficient": {"type": "boolean"},
    },
    "required": ["answer", "confidence", "sufficient"],
}


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


def compose_answer(
    query: str, pages: list[PageContent], store: LibraryStore, *, llm: LLM | None = None
) -> Answer:
    """Answer strictly from the read pages. Insufficient evidence → not_found status."""
    llm = llm or get_llm()
    blocks = "\n\n".join(
        f"[EVIDENCE {i + 1} — {store.path_str(p.page_id)}]\n<<<\n{p.markdown}\n>>>"
        for i, p in enumerate(pages)
    )
    prompt = llm.load_prompt("answer", query=query, evidence=blocks)
    data = llm.generate_json(prompt, schema=ANSWER_SCHEMA)

    citations = [Citation(path=store.path_str(p.page_id), page_id=p.page_id) for p in pages]
    if not data.get("sufficient", True):
        closest = [store.path_str(p.page_id) for p in pages]
        return compose_not_found(query, closest, note=data.get("answer", ""))
    return Answer(
        text=data.get("answer", "").strip(),
        status="answered",
        confidence=data.get("confidence", "medium"),
        citations=citations,
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


def path_refs(store: LibraryStore, page_id: str) -> list[NodeRef]:
    return store.path_of(page_id)
