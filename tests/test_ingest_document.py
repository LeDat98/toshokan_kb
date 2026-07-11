"""Document-ingest tests. parse/split are LLM-free; classify/pipeline use a fake LLM."""

import pytest

from libkb import seed
from libkb.ingest.classify import classify_placement
from libkb.ingest.parse import ParsedDoc, parse_source
from libkb.ingest.pipeline import approve_placement, ingest_document, list_uncatalogued
from libkb.ingest.split import split_document
from libkb.library.store import LibraryStore

DOC = """# Vector Databases

Intro paragraph before any section heading.

## What they are
A vector database stores embeddings and does nearest-neighbor search over them.

## HNSW vs IVF
HNSW is a graph index; IVF clusters vectors. Both trade recall for speed.

## Filtering
Metadata filters narrow the candidate set before or after search.
"""


class FakeClassifierLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def load_prompt(self, name, **kw):
        return name

    def generate_json(self, contents, *, schema, **kw):
        self.calls += 1
        return self.payload


@pytest.fixture
def store(tmp_path):
    s = LibraryStore(tmp_path / "library")
    s.init_library()
    seed.apply(s)  # gives an existing AI domain with RAG/LLM/CV shelves
    return s


# ---------------------------------------------------------------- parse / split


def test_parse_markdown(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("---\ntitle: My Doc\n---\n\n# My Doc\n\nBody.\n", encoding="utf-8")
    doc = parse_source(f)
    assert doc.title == "My Doc"
    assert doc.source_type == "md"
    assert "Body." in doc.markdown


def test_parse_unsupported(tmp_path):
    from libkb.exceptions import IngestError

    f = tmp_path / "x.docx"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(IngestError):
        parse_source(f)


def test_split_on_headings():
    doc = ParsedDoc(title="Vector Databases", markdown=DOC, source_ref="doc.md", source_type="md")
    book = split_document(doc)
    titles = [p.title for p in book.pages]
    assert "Overview" in titles  # the preamble
    assert "HNSW vs IVF" in titles
    assert "Filtering" in titles
    hnsw = next(p for p in book.pages if p.title == "HNSW vs IVF")
    assert "graph index" in hnsw.body_markdown


def test_split_without_headings_falls_back_to_size():
    body = ("A paragraph of text. " * 60 + "\n\n") * 4
    doc = ParsedDoc(title="Blob", markdown=body, source_ref="b.txt", source_type="txt")
    book = split_document(doc)
    assert len(book.pages) >= 2
    assert all(p.title.startswith("Part ") for p in book.pages)


# ---------------------------------------------------------------- classify


def test_classify_reconciles_existing_domain(store):
    book = split_document(
        ParsedDoc(title="Reranking notes", markdown=DOC, source_ref="d.md", source_type="md")
    )
    llm = FakeClassifierLLM(
        {"domain_title": "AI", "shelf_title": "RAG", "confidence": 0.9, "rationale": "fits RAG"}
    )
    placement = classify_placement(book, store, llm=llm)
    assert placement.domain_is_new is False  # AI exists → reconciled
    assert placement.shelf_is_new is False  # RAG exists
    assert placement.domain_id and placement.shelf_id


def test_classify_new_domain(store):
    book = split_document(
        ParsedDoc(title="Quantum", markdown=DOC, source_ref="q.md", source_type="md")
    )
    llm = FakeClassifierLLM(
        {"domain_title": "Physics", "shelf_title": "Quantum", "confidence": 0.4, "rationale": "new"}
    )
    placement = classify_placement(book, store, llm=llm)
    assert placement.domain_is_new is True
    assert placement.domain_id is None


# ---------------------------------------------------------------- pipeline


def _doc_file(tmp_path):
    f = tmp_path / "vector-databases.md"
    f.write_text(DOC, encoding="utf-8")
    return f


def test_ingest_files_confident_doc(store, tmp_path):
    llm = FakeClassifierLLM(
        {"domain_title": "AI", "shelf_title": "RAG", "confidence": 0.9, "rationale": "fits"}
    )
    outcome = ingest_document(_doc_file(tmp_path), store, llm=llm)
    assert outcome.status == "filed"
    assert not outcome.gated
    assert outcome.book_path.startswith("AI ▸ RAG ▸ Vector Databases")
    assert outcome.n_pages >= 3
    # the book is really in the tree now
    book_id = store.resolve_path("ai/rag/vector-databases")
    assert store.toc(book_id).chapters


def test_ingest_gates_low_confidence_into_uncatalogued(store, tmp_path):
    llm = FakeClassifierLLM(
        {
            "domain_title": "Physics",
            "shelf_title": "Quantum",
            "confidence": 0.4,
            "rationale": "brand-new domain",
        }
    )
    outcome = ingest_document(_doc_file(tmp_path), store, llm=llm)
    assert outcome.status == "uncatalogued"
    assert outcome.gated
    # not created a Physics domain in the main tree
    from libkb.exceptions import NodeNotFound

    with pytest.raises(NodeNotFound):
        store.resolve_path("physics")

    queue = list_uncatalogued(store)
    row = next(r for r in queue if r["title"] == "Vector Databases")
    assert row["proposed_domain"] == "Physics"
    assert row["confidence"] == 0.4

    new_path = approve_placement(store, row["id"], "AI", "Infrastructure")
    assert new_path == "AI ▸ Infrastructure ▸ Vector Databases"
    assert list_uncatalogued(store) == []  # moved out of the queue
