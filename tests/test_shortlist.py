"""A shelf too wide to render: shortlist, never re-gate (docs/ROUTING_REDESIGN.md §7).

The temptation, when a shelf has 200 pages, is to put the book gate back. That is the exact mistake
Part I of the redesign exists to undo — an irreversible commitment made on partial information.

The evidenced alternative is two-stage: **narrow to ~5–8 candidates, then let the librarian
compare.** The catalog earns that job on measurement (`libkb probe-recall`): on questions the
generator never anticipated, its top-1 is only 39.3%, but the right page is in its **top-10 90.7%**
of the time. A bad oracle; a good sieve.

And §7.4's rule, which these tests exist to enforce: **a shortlist the librarian cannot escape is
`open_book` all over again.** 9.3% of the time the right page is NOT in the top-10 — so the escape
hatch must be real, and it must still work.

All LLM-free: the embedder is a scripted fake whose geometry is the assertion.
"""

import numpy as np
import pytest

from libkb import seed
from libkb.agent.tools import Navigation
from libkb.catalog.store import Catalog
from libkb.config import get_settings
from libkb.library.store import LibraryStore


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    # force every shelf to be "too wide" so the shortlist path is the one under test
    monkeypatch.setenv("LIBKB_MAX_SHELF_TOC_ENTRIES", "2")
    monkeypatch.setenv("LIBKB_SHELF_SHORTLIST_K", "3")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store(tmp_path):
    s = LibraryStore(tmp_path / "library")
    s.init_library()
    seed.apply(s)
    return s


def _unit(*values) -> np.ndarray:
    v = np.asarray([values], dtype=np.float32)
    return v / np.linalg.norm(v)


class FakeEmbedder:
    """Embeds the query onto whichever page's title it was told to favour."""

    def __init__(self, placements: dict[str, tuple], target: str):
        self._placements = placements
        self._target = target
        self.embed_calls = 0

    def embed(self, texts, *, task="RETRIEVAL_DOCUMENT", model=None):
        self.embed_calls += 1
        return _unit(*self._placements[self._target])

    def load_prompt(self, name, **kw):
        return f"[{name}]"


def _rag_shelf(store, tmp_path, favour_title):
    """Catalog over the RAG shelf's pages; the query lands on `favour_title`."""
    shelf = store.resolve_path("ai/rag")
    pages = [
        (p, book)
        for book in store.children(shelf)
        if book.kind == "book"
        for p in store.children(book.id)
        if p.kind == "page"
    ]
    # each page gets its own axis; the query will be embedded exactly onto one of them
    placements = {}
    for i, (p, _) in enumerate(pages):
        vec = [0.0] * len(pages)
        vec[i] = 1.0
        placements[p.title] = tuple(vec)

    cat = Catalog(tmp_path / "catalog.db")
    for p, book in pages:
        cat.add_page(
            page_id=p.id,
            book_id=book.id,
            path=store.path_str(p.id),
            texts=[f"q about {p.title}"],
            langs=["en"],
            embeddings=_unit(*placements[p.title]),
        )
    llm = FakeEmbedder(placements, favour_title)
    return cat, llm, [p.title for p, _ in pages]


def _at_shelf(store, cat, llm, query):
    nav = Navigation(store, get_settings(), catalog=cat, llm=llm, query=query)
    nav.start_menu()
    nav.execute("browse", {"target": "AI"})
    nav.execute("browse", {"target": "RAG"})
    return nav


def test_a_wide_shelf_is_shortlisted_not_re_gated(store, tmp_path):
    cat, llm, titles = _rag_shelf(store, tmp_path, "Reranking & Cross-encoders")
    nav = _at_shelf(store, cat, llm, "how do I rerank results?")
    out = nav.execute("open_shelf", {})
    cat.close()

    assert "The card catalog ranked them against your question" in out.text
    assert "Reranking & Cross-encoders" in out.text  # the page the query was pointed at
    assert llm.embed_calls == 1  # one embed for the shelf, not one per page
    assert "shortlisted" in out.event.detail

    # the shortlist is capped, and it is a strict subset of the shelf
    listed = [t for t in titles if f'"{t}"' in out.text]
    assert len(listed) == 3  # LIBKB_SHELF_SHORTLIST_K
    assert len(listed) < len(titles)


def test_the_shortlisted_pages_are_readable(store, tmp_path):
    cat, llm, _ = _rag_shelf(store, tmp_path, "Reranking & Cross-encoders")
    nav = _at_shelf(store, cat, llm, "how do I rerank results?")
    nav.execute("open_shelf", {})
    out = nav.execute("read_page", {"title": "Reranking & Cross-encoders"})
    cat.close()

    assert out.text.startswith("[PAGE")
    assert nav.state.pages_read == 1


def test_the_shortlist_is_a_hint_and_the_escape_hatch_really_works(store, tmp_path):
    """§7.4. The catalog misses the right page 9.3% of the time. If the librarian cannot get out of
    the shortlist, those cases are lost forever — which is exactly the open_book trap, rebuilt."""
    cat, llm, _ = _rag_shelf(store, tmp_path, "Reranking & Cross-encoders")
    nav = _at_shelf(store, cat, llm, "how do I rerank results?")
    out = nav.execute("open_shelf", {})

    assert "The catalog is a suggestion, not a verdict" in out.text
    assert "more pages on this shelf" in out.text
    assert "open_book" in out.text

    # a page the catalog did NOT shortlist is still reachable — by escaping into its book
    assert "What is RAG" not in out.text  # not shortlisted (the query pointed elsewhere)
    nav.execute("open_book", {"title": "RAG Fundamentals"})
    read = nav.execute("read_page", {"title": "What is RAG"})
    cat.close()
    assert read.text.startswith("[PAGE")  # the answer was never deleted from the universe


def test_no_catalog_falls_back_to_the_book_gate_and_says_so(store):
    """Degrade honestly. Without a catalog there is nothing to shortlist with, so the book gate is
    the only option left — but the walk must not silently pretend it shortlisted."""
    nav = Navigation(store, get_settings(), query="anything")  # no catalog, no llm
    nav.start_menu()
    nav.execute("browse", {"target": "AI"})
    nav.execute("browse", {"target": "RAG"})
    out = nav.execute("open_shelf", {})

    assert "card catalog is unavailable" in out.text
    assert "open_book" in out.text
    assert nav.state.current_toc == {}  # nothing laid out ⇒ read_page must not resolve


def test_a_flaky_embed_degrades_to_the_book_gate_instead_of_breaking_the_walk(store, tmp_path):
    cat, llm, _ = _rag_shelf(store, tmp_path, "Reranking & Cross-encoders")

    def boom(*a, **kw):
        raise RuntimeError("embedding service is down")

    llm.embed = boom
    nav = _at_shelf(store, cat, llm, "how do I rerank results?")
    out = nav.execute("open_shelf", {})
    cat.close()

    assert "card catalog is unavailable" in out.text
    assert out.event is not None  # the walk goes on
