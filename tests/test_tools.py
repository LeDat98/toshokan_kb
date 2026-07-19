"""Navigation tool + budget tests — no LLM."""

import pytest

from libkb import seed
from libkb.agent.tools import Navigation
from libkb.config import Settings
from libkb.library.store import LibraryStore


@pytest.fixture
def nav(tmp_path_factory):
    store = LibraryStore(tmp_path_factory.mktemp("lib") / "library")
    store.init_library()
    seed.apply(store)
    settings = Settings(_env_file=None, gemini_api_key="x", max_hops=4, max_pages_per_nav=2)
    return Navigation(store, settings)


def test_start_menu_lists_domains(nav):
    menu = nav.start_menu()
    assert "AI" in menu
    assert "entrance" in menu


def test_walk_to_reranking_page(nav):
    nav.start_menu()
    assert "RAG" in nav.execute("browse", {"target": "AI"}).text
    assert "Advanced RAG Techniques" in nav.execute("browse", {"target": "RAG"}).text
    toc = nav.execute("open_book", {"title": "Advanced RAG Techniques"}).text
    assert "Reranking" in toc
    page = nav.execute("read_page", {"title": "Reranking & Cross-encoders"}).text
    assert "cross-encoder" in page.lower()
    assert "<<<" in page  # delimited evidence block
    assert nav.state.pages_read == 1


def test_browse_unknown_child_is_forgiving_message(nav):
    nav.start_menu()
    out = nav.execute("browse", {"target": "Nonexistent"})
    assert out.terminal is None
    assert "No" in out.text and "AI" in out.text  # lists available options


def test_browse_a_book_lays_out_its_pages(nav):
    """browse() is tolerant of a book target. In shelf mode (the default) that lays out the whole
    shelf rather than committing to the book — either way the book's pages become readable."""
    nav.start_menu()
    nav.execute("browse", {"target": "AI"})
    nav.execute("browse", {"target": "RAG"})
    out = nav.execute("browse", {"target": "Advanced RAG Techniques"})  # a book, not a shelf
    assert "Reranking & Cross-encoders" in out.text
    assert nav.execute("read_page", {"title": "Reranking & Cross-encoders"}).text.startswith(
        "[PAGE"
    )


def test_hop_budget_forces_not_found(nav):
    nav.start_menu()
    nav.execute("browse", {"target": "AI"})  # hop 1
    nav.execute("browse", {"target": "RAG"})  # hop 2
    nav.execute("open_book", {"title": "Advanced RAG Techniques"})  # hop 3
    nav.execute("open_book", {"title": "RAG Fundamentals"})  # hop 4 (== max_hops, allowed)
    over = nav.execute("open_book", {"title": "RAG Evaluation"})  # hop 5 > 4 → budget
    assert over.terminal is not None
    assert over.terminal.status == "NOT_FOUND"
    assert "budget" in over.terminal.reason


def test_read_page_budget(nav):
    nav.start_menu()
    nav.execute("browse", {"target": "AI"})
    nav.execute("browse", {"target": "RAG"})
    nav.execute("open_book", {"title": "RAG Fundamentals"})
    nav.execute("read_page", {"title": "What is RAG"})
    nav.execute("read_page", {"title": "Chunking Strategies"})
    # max_pages_per_nav=2 reached
    out = nav.execute("read_page", {"title": "Embeddings & Indexing"})
    assert "budget" in out.text.lower()
    assert nav.state.pages_read == 2


def test_found_requires_a_read_page(nav):
    nav.start_menu()
    out = nav.execute("found", {"note": "done"})
    assert out.terminal is None
    assert "read_page" in out.text


def test_found_after_reading_concludes(nav):
    nav.start_menu()
    nav.execute("browse", {"target": "AI"})
    nav.execute("browse", {"target": "RAG"})
    nav.execute("open_book", {"title": "Advanced RAG Techniques"})
    nav.execute("read_page", {"title": "Reranking & Cross-encoders"})
    out = nav.execute("found", {"note": "answer is on the reranking page"})
    assert out.terminal is not None
    assert out.terminal.status == "FOUND"
    assert len(out.terminal.page_ids) == 1


def test_go_back_counts_backtracks(nav):
    nav.start_menu()
    nav.execute("browse", {"target": "AI"})
    nav.execute("go_back", {"reason": "wrong hall"})
    assert nav.state.backtracks == 1
    assert nav.state.cursor  # back at root


def test_not_found_uses_provided_closest(nav):
    nav.start_menu()
    out = nav.execute("not_found", {"reason": "no QEC", "closest": ["AI ▸ ML"]})
    assert out.terminal.status == "NOT_FOUND"
    assert out.terminal.closest == ["AI ▸ ML"]
