"""A menu line is a SPINE LABEL, not an abstract (docs/ROUTING_REDESIGN.md §0a).

The folder import copied whole frontmatter `description:` fields into `TOCEntry.one_line` —
measured on the live library: median 1013 chars, max 1436. That was roughly half of every query's
input tokens (a menu is resent on every later turn) and it made every option in a menu sound
equally relevant, which is the documented cause of LLM mis-selection among similar categories.

Two independent defences, both tested here:
  1. render time — the stored value is never trusted, so existing libraries are fixed with no
     migration and a future ingest regression cannot leak back into the walk;
  2. ingest time — the source of the bloat is capped where it is written.

All LLM-free.
"""

import pytest

from libkb import seed
from libkb.agent.tools import Navigation
from libkb.config import get_settings
from libkb.ingest.survey import _page_from_md
from libkb.library.store import LibraryStore

ESSAY = "Nội dung dài. " + ("this sentence pretends to be a one-line summary. " * 40)  # ~2000 chars


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


def _bloat_a_page(store) -> str:
    """Give one real page an essay-length one_line, exactly as the retail import did."""
    book_id = store.resolve_path("ai/rag/rag-fundamentals")
    meta = store.write_page(book_id, "Bloated Page", "# Bloated Page\n\nbody", one_line=ESSAY)
    return meta.id


def _at_rag_shelf(store):
    nav = Navigation(store, get_settings())
    nav.start_menu()
    nav.execute("browse", {"target": "AI"})
    nav.execute("browse", {"target": "RAG"})
    return nav


def _bloated_row(text: str) -> str:
    return next(line for line in text.splitlines() if "Bloated Page" in line)


# ------------------------------------------------------------------ render-time cap


def test_shelf_menu_caps_a_stored_essay(store):
    _bloat_a_page(store)
    nav = _at_rag_shelf(store)
    out = nav.execute("open_shelf", {})

    row = _bloated_row(out.text)
    assert len(row) < 200  # title + a 120-char spine, not a 2000-char essay
    assert row.endswith("…")  # truncated, and visibly so
    assert ESSAY not in out.text


def test_book_toc_caps_a_stored_essay(store, monkeypatch):
    monkeypatch.setenv("LIBKB_ROUTING_MODE", "book")
    get_settings.cache_clear()
    _bloat_a_page(store)
    nav = _at_rag_shelf(store)
    out = nav.execute("open_book", {"title": "RAG Fundamentals"})
    assert len(_bloated_row(out.text)) < 200
    assert ESSAY not in out.text


def test_child_menu_caps_a_stored_essay(store):
    """Domain/shelf/book cards get their one_line from the node description — cap that too."""
    shelf_id = store.resolve_path("ai/rag")
    store.set_description(shelf_id, ESSAY, 1)
    nav = Navigation(store, get_settings())
    nav.start_menu()
    out = nav.execute("browse", {"target": "AI"})
    rag_row = next(line for line in out.text.splitlines() if '"RAG"' in line)
    assert len(rag_row) < 200
    assert ESSAY not in rag_row


def test_the_cap_is_configurable(store, monkeypatch):
    monkeypatch.setenv("LIBKB_MAX_ONE_LINE_CHARS", "20")
    get_settings.cache_clear()
    _bloat_a_page(store)
    nav = _at_rag_shelf(store)
    assert len(_bloated_row(nav.execute("open_shelf", {}).text)) < 60


# ------------------------------------------------------------------ the scale guard


def test_shelf_falls_back_when_the_menu_is_too_many_tokens(store, monkeypatch):
    """The old guard counted ROWS. A 50-page shelf passed it while emitting a ~14k-token menu that
    every later turn then resent. Rows and tokens are different ceilings; both must hold."""
    monkeypatch.setenv("LIBKB_MAX_SHELF_TOC_ENTRIES", "999")  # rows: never trips
    monkeypatch.setenv("LIBKB_MAX_SHELF_MENU_TOKENS", "50")  # tokens: trips immediately
    get_settings.cache_clear()

    nav = _at_rag_shelf(store)
    out = nav.execute("open_shelf", {})
    assert "too many to lay out at once" in out.text
    assert "tokens" in (out.event.detail if out.event else "")
    assert nav.state.current_toc == {}  # nothing laid out ⇒ read_page must not resolve


def test_a_normal_shelf_reports_its_token_weight(store):
    nav = _at_rag_shelf(store)
    out = nav.execute("open_shelf", {})
    assert "too many" not in out.text
    assert "tokens" in out.event.detail  # the cost of the menu is visible in the trace
    assert nav.state.current_toc  # …and the pages ARE laid out


# ------------------------------------------------------------------ ingest-time cap


def test_ingest_does_not_write_an_essay_into_one_line(tmp_path):
    """The source of the bloat: a frontmatter `description:` is an abstract; one_line is a label."""
    md = tmp_path / "page.md"
    md.write_text(f"---\ntitle: A Page\ndescription: {ESSAY}\n---\n\n# A Page\n\nbody", "utf-8")

    page = _page_from_md(md, tmp_path)
    assert page.title == "A Page"
    assert len(page.one_line) <= get_settings().max_one_line_chars
    assert page.one_line.startswith("Nội dung dài")  # capped, not dropped
