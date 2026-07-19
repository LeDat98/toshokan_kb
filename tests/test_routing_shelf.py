"""Shelf-mode routing (docs/ROUTING_REDESIGN.md §2): the book is storage, not a decision.

The property that matters: standing on a shelf, the librarian can read ANY page on it without
ever committing to a book — so a wrong book choice can no longer put the right page out of reach.
All LLM-free (scripted fake LLM).
"""

import pytest

from libkb import seed
from libkb.agent.navigator import navigate
from libkb.agent.tools import Navigation
from libkb.config import get_settings
from libkb.library.store import LibraryStore
from libkb.llm.client import LLMResult, ToolCall


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store(tmp_path):
    s = LibraryStore(tmp_path / "library")
    s.init_library()
    seed.apply(s)
    return s


class ScriptLLM:
    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

    def load_prompt(self, name, **kw):
        self.prompt_name = name
        return f"[{name}]"

    def generate(self, contents, **kwargs):
        if self.calls < len(self._script):
            name, args = self._script[self.calls]
            self.calls += 1
            return LLMResult(text=None, tool_calls=[ToolCall(name=name, args=args)])
        self.calls += 1
        return LLMResult(text="", tool_calls=[ToolCall(name="not_found", args={"reason": "end"})])


def _at_rag_shelf(store):
    nav = Navigation(store, get_settings())
    nav.start_menu()  # populates the root menu so browse() can resolve
    nav.execute("browse", {"target": "AI"})
    nav.execute("browse", {"target": "RAG"})
    return nav


def test_open_shelf_lays_out_every_book_on_the_shelf(store):
    nav = _at_rag_shelf(store)
    out = nav.execute("open_shelf", {})

    # every book on the RAG shelf appears as a grouping header…
    assert 'From "Advanced RAG Techniques"' in out.text
    assert 'From "RAG Fundamentals"' in out.text
    # …and pages from DIFFERENT books are all readable in one menu
    assert "Reranking & Cross-encoders" in out.text  # Advanced RAG Techniques
    assert "What is RAG" in out.text  # RAG Fundamentals
    assert out.event is not None and out.event.action == "shelf"
    assert nav.state.open_book_id is None  # no book was committed to


def test_read_page_without_ever_choosing_a_book(store):
    """The whole point: the page is reachable without an open_book commitment."""
    nav = _at_rag_shelf(store)
    nav.execute("open_shelf", {})
    out = nav.execute("read_page", {"title": "Reranking & Cross-encoders"})
    assert "cross-encoder" in out.text.lower()
    assert nav.state.pages_read == 1


def test_open_book_is_a_forgiving_alias_in_shelf_mode(store):
    nav = _at_rag_shelf(store)
    out = nav.execute("open_book", {"title": "RAG Fundamentals"})
    assert "do not need to pick a book" in out.text
    assert 'From "Advanced RAG Techniques"' in out.text  # siblings are shown too
    # and a page from the OTHER book is still readable
    assert nav.execute("read_page", {"title": "Reranking & Cross-encoders"}).text.startswith(
        "[PAGE"
    )


def test_open_shelf_refuses_when_not_on_a_shelf(store):
    nav = Navigation(store, get_settings())  # still at the root
    assert "standing on a shelf" in nav.execute("open_shelf", {}).text


def test_wide_shelf_falls_back_to_book_by_book(store, monkeypatch):
    monkeypatch.setenv("LIBKB_MAX_SHELF_TOC_ENTRIES", "2")
    get_settings.cache_clear()
    nav = _at_rag_shelf(store)
    out = nav.execute("open_shelf", {})
    assert "too many to lay out at once" in out.text
    assert "open_book(" in out.text
    assert nav.state.current_toc == {}  # nothing laid out → read_page must not resolve


def test_navigate_uses_shelf_prompt_and_tool(store):
    fake = ScriptLLM(
        [
            ("browse", {"target": "AI"}),
            ("browse", {"target": "RAG"}),
            ("open_shelf", {}),
            ("read_page", {"title": "Reranking & Cross-encoders"}),
            ("found", {"note": "here"}),
        ]
    )
    result = navigate("what is reranking?", store=store, llm=fake)
    assert result.status == "FOUND"
    assert fake.prompt_name == "route_shelf"
    assert any(e.action == "shelf" for e in result.events)


def test_book_mode_still_works(store, monkeypatch):
    """The legacy path must stay alive so the A/B can be re-run."""
    monkeypatch.setenv("LIBKB_ROUTING_MODE", "book")
    get_settings.cache_clear()
    fake = ScriptLLM(
        [
            ("browse", {"target": "AI"}),
            ("browse", {"target": "RAG"}),
            ("open_book", {"title": "Advanced RAG Techniques"}),
            ("read_page", {"title": "Reranking & Cross-encoders"}),
            ("found", {"note": "here"}),
        ]
    )
    result = navigate("what is reranking?", store=store, llm=fake)
    assert result.status == "FOUND"
    assert fake.prompt_name == "route"
    assert any(e.action == "open" for e in result.events)  # it DID commit to a book
