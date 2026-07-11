import pytest

from libkb import seed
from libkb.library.store import LibraryStore


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    store = LibraryStore(tmp_path_factory.mktemp("lib") / "library")
    store.init_library()
    stats = seed.apply(store)
    return store, stats


def test_seed_counts(seeded):
    _, stats = seeded
    assert stats.n_books == 6
    assert stats.n_pages == 16
    assert stats.n_shelves == 4  # RAG, LLM, CV + Uncatalogued


def test_reranking_page_is_findable_and_substantive(seeded):
    store, _ = seeded
    book_id = store.resolve_path("ai/rag/advanced-rag-techniques")
    toc = store.toc(book_id)
    entry = next(
        e for c in toc.chapters for e in c.entries if e.title == "Reranking & Cross-encoders"
    )
    page = store.page(entry.page_id)
    assert "cross-encoder" in page.markdown.lower()
    assert "two-stage" in page.markdown.lower()
    assert store.path_str(entry.page_id).startswith("AI ▸ RAG ▸ Advanced RAG Techniques")


def test_descriptions_are_discriminative(seeded):
    store, _ = seeded
    rag = store.get(store.resolve_path("ai/rag"))
    llm = store.get(store.resolve_path("ai/llm"))
    # the "does NOT cover X — see Y" convention that routing depends on
    assert "NOT" in rag.description and "LLM" in rag.description
    assert "NOT" in llm.description and "RAG" in llm.description


def test_see_also_example_exists(seeded):
    store, _ = seeded
    rag = store.get(store.resolve_path("ai/rag"))
    assert any(sa.target.title == "LLM" for sa in rag.see_also)
