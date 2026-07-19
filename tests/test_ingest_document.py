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


def test_small_unstructured_doc_stays_one_page():
    """Size is a GUARD, not a strategy: a short blob with no headings is one page."""
    body = ("A paragraph of text. " * 60 + "\n\n") * 4  # ~4.8k chars, under the 2000-token budget
    doc = ParsedDoc(title="Blob", markdown=body, source_ref="b.txt", source_type="txt")
    book = split_document(doc)
    assert len(book.pages) == 1
    assert book.pages[0].title == "Blob"


def test_split_without_headings_falls_back_to_size_only_when_oversized():
    body = ("A paragraph of text. " * 60 + "\n\n") * 12  # ~14k chars — over budget, no structure
    doc = ParsedDoc(title="Blob", markdown=body, source_ref="b.txt", source_type="txt")
    book = split_document(doc)
    assert len(book.pages) >= 2
    assert all(p.title.startswith("Blob (") for p in book.pages)  # named, so it can be cited


def test_oversized_section_is_cut_at_its_own_headings():
    """The bug this rule exists for: a `3 Methodology` page of 9,992 chars that had 12 unused
    sub-headings inside it. Structure is spent before size ever gets a vote."""
    filler = "Lorem ipsum dolor sit amet. " * 130  # ~3.6k chars per subsection
    md = "## 1 Intro\n\nShort.\n\n## 3 Methodology\n\nLead-in.\n\n" + "\n\n".join(
        f"### 3.{i} Step {i}\n\n{filler}" for i in (1, 2, 3)
    )
    doc = ParsedDoc(title="Paper", markdown=md, source_ref="p.pdf", source_type="pdf")
    book = split_document(doc)
    titles = [p.title for p in book.pages]

    assert "3 Methodology" not in titles  # the 10k-char page is gone
    assert any(t.startswith("3 Methodology — 3.") for t in titles)  # cut at ITS headings
    assert all("Lorem" not in t for t in titles)  # …not by size
    budget = 2000 * 4
    assert all(len(p.body_markdown) <= budget for p in book.pages if p.title.startswith("3 "))


def test_back_matter_is_kept_but_never_indexed():
    md = "## 1 Intro\n\nBody text here.\n\n## References\n\n[1] Someone. A paper. 2020.\n"
    doc = ParsedDoc(title="Paper", markdown=md, source_ref="p.pdf", source_type="pdf")
    pages = {p.title: p for p in split_document(doc).pages}

    assert "References" in pages  # still on the shelf — a citation may want it
    assert pages["References"].indexable is False  # …but never in the sieve
    assert pages["1 Intro"].indexable is True


def test_tiny_back_matter_is_not_folded_into_knowledge():
    """A 30-char bibliography must not sneak back into the catalog on the arm of the section
    above it — the merge rule is where that would happen."""
    md = "## 1 Intro\n\n" + "Body. " * 40 + "\n\n## References\n\n[1] X.\n"
    doc = ParsedDoc(title="Paper", markdown=md, source_ref="p.pdf", source_type="pdf")
    pages = {p.title: p.indexable for p in split_document(doc).pages}
    assert pages.get("References") is False


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


def test_slug_is_bounded_but_the_title_is_not():
    """A title is prose; a slug is a filename. A 200-char news headline nested under
    library/domains/…/shelves/…/books/…/pages/ crashes Windows at 260 chars — it did, on the
    MultiHop corpus. The full title still lives inside the file; only the NAME is cut."""
    from libkb.library.models import MAX_SLUG, slugify

    headline = (
        "Attorney general going after Jeffrey Epstein's estate says she was fired for her "
        "dogged pursuit: 'My bar license, my integrity were more important to me'"
    )
    slug = slugify(headline)
    assert len(slug) <= MAX_SLUG
    assert not slug.endswith("-")
    assert slugify("") == "untitled"


def test_a_split_file_is_not_named_after_itself_twice():
    """`split.py` already names its size-slices `<title> (1/5)`. Prefixing the file title again
    produced `Long headline … — Long headline … (1/5)` — the title twice, 250+ chars, and the
    filename that crashed the import."""
    from libkb.ingest.survey import _qualify

    assert _qualify("Big News", "Big News (1/5)", 0) == "Big News (1/5)"  # already qualified
    assert _qualify("Big News", "3 Methodology", 0) == "Big News — 3 Methodology"
    assert _qualify("Big News", "", 2) == "Big News (3)"


def test_document_title_is_cleaned_not_just_sections():
    """A whole book was named `**PDF Retrieval Augmented Question Answering**` because clean_title
    was applied to section headings but not to the DOCUMENT title (the funnel in parse.py)."""
    doc = ParsedDoc(
        title="**PDF Retrieval Augmented Question Answering**",
        markdown="# **PDF Retrieval Augmented Question Answering**\n\n## Intro\n\nBody.\n",
        source_ref="p.pdf",
        source_type="pdf",
    )
    from libkb.ingest.parse import _title_from

    assert _title_from(doc.markdown, "fallback") == "PDF Retrieval Augmented Question Answering"
