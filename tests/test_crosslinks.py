"""Cross-references: one physical location, many access points (ROUTING_REDESIGN §8.1).

The misshelved probe finds pages that fit another book better than their own — 49% of the live
library. That is not a filing-error rate; most of those pages are genuinely two-faceted (a KPI
*definition* about *inventory* belongs to both books) and a single-parent tree just forces a choice.
So the output is a cross-reference, never a move.

The property that makes a cross-reference worth anything: **the librarian can FOLLOW it.** A link he
can see but not read is decoration. All LLM-free — the probe reads vectors, the writer reads the
probe.
"""

import numpy as np
import pytest

from libkb import seed
from libkb.agent.tools import Navigation
from libkb.catalog.store import Catalog
from libkb.config import get_settings
from libkb.evals.misshelved import probe_misshelved
from libkb.library.crosslinks import ORIGIN, build_crosslinks
from libkb.library.models import ROOT_ID
from libkb.library.store import LibraryStore


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


def _vec(*values) -> np.ndarray:
    v = np.asarray([values], dtype=np.float32)
    return v / np.linalg.norm(v)


def _catalog(store, tmp_path, placements):
    """placements: {page_id: (x, y, z)} — hand-placed vectors so the geometry is the assertion."""
    cat = Catalog(tmp_path / "catalog.db")
    for page_id, coords in placements.items():
        meta = store.get(page_id)
        cat.add_page(
            page_id=page_id,
            book_id=meta.parent_id,
            path=store.path_str(page_id),
            texts=[f"q for {meta.title}"],
            langs=["en"],
            embeddings=_vec(*coords),
        )
    return cat


def _pages_of(store, human_path):
    book = store.resolve_path(human_path)
    return [c.id for c in store.children(book) if c.kind == "page"]


# ------------------------------------------------------------------ the probe


def test_probe_finds_the_page_that_sits_with_the_wrong_book(store, tmp_path):
    """One page in RAG Fundamentals is planted in the LLM shelf's region of the space. The probe
    must name it — and name the book it actually belongs near."""
    rag = _pages_of(store, "ai/rag/rag-fundamentals")
    llm = _pages_of(store, "ai/llm/llm-foundations")
    placements = {p: (1.0, 0.0, 0.0) for p in rag}
    placements |= {p: (0.0, 1.0, 0.0) for p in llm}
    stray = rag[0]
    placements[stray] = (0.05, 1.0, 0.0)  # filed in RAG, lives among the LLM pages

    cat = _catalog(store, tmp_path, placements)
    report = probe_misshelved(cat)
    cat.close()

    hit = next(h for h in report.hits if h.page_id == stray)
    assert hit.own_book == "RAG Fundamentals"
    assert hit.best_book == "LLM Foundations"
    assert hit.cross_shelf  # RAG and LLM are different shelves
    assert hit.delta > 0


def test_a_page_that_sits_with_its_own_book_is_not_reported(store, tmp_path):
    rag = _pages_of(store, "ai/rag/rag-fundamentals")
    llm = _pages_of(store, "ai/llm/llm-foundations")
    cat = _catalog(
        store,
        tmp_path,
        {p: (1.0, 0.0, 0.0) for p in rag} | {p: (0.0, 1.0, 0.0) for p in llm},
    )
    report = probe_misshelved(cat)
    cat.close()
    assert [h.page_id for h in report.hits if h.page_id in rag] == []


# ------------------------------------------------------------------ writing the links


def _planted(store, tmp_path):
    rag = _pages_of(store, "ai/rag/rag-fundamentals")
    llm = _pages_of(store, "ai/llm/llm-foundations")
    placements = {p: (1.0, 0.0, 0.0) for p in rag} | {p: (0.0, 1.0, 0.0) for p in llm}
    placements[rag[0]] = (0.05, 1.0, 0.0)
    return _catalog(store, tmp_path, placements), rag[0]


def test_the_link_is_written_on_the_book_the_reader_would_search(store, tmp_path):
    """Direction matters and it is the reverse of what feels natural. The page is filed in RAG but
    looks like LLM, so a reader asking about its content is routed to LLM — where it is NOT. The
    cross-reference therefore goes ON the LLM book, POINTING AT the RAG page."""
    cat, stray = _planted(store, tmp_path)
    report = build_crosslinks(store, cat, min_delta=0.0, max_per_book=3)
    cat.close()

    assert report.written == 1
    llm_book = store.get(store.resolve_path("ai/llm/llm-foundations"))
    [link] = [sa for sa in llm_book.see_also if sa.origin == ORIGIN]
    assert link.target.id == stray  # points at the page that lives elsewhere

    rag_book = store.get(store.resolve_path("ai/rag/rag-fundamentals"))
    assert not rag_book.see_also  # the page's OWN book gets nothing — it already has the page


def test_regeneration_clears_stale_links_but_never_manual_ones(store, tmp_path):
    cat, _ = _planted(store, tmp_path)
    llm_id = store.resolve_path("ai/llm/llm-foundations")
    cv_id = store.resolve_path("ai/cv")
    store.add_see_also(llm_id, cv_id, "a human wrote this", origin="manual")

    build_crosslinks(store, cat, min_delta=0.0, max_per_book=3)
    assert len(store.get(llm_id).see_also) == 2

    # now the evidence disappears — the machine link must go, the human link must stay
    cat.clear()
    report = build_crosslinks(store, cat, min_delta=0.0, max_per_book=3)
    cat.close()
    assert report.cleared == 1 and report.written == 0
    [survivor] = store.get(llm_id).see_also
    assert survivor.origin == "manual"


def test_a_weak_pull_is_not_a_cross_reference(store, tmp_path):
    cat, _ = _planted(store, tmp_path)
    report = build_crosslinks(store, cat, min_delta=0.99)  # nothing pulls THAT hard
    cat.close()
    assert report.written == 0 and report.skipped_below_floor >= 1


def test_same_shelf_pulls_are_skipped(store, tmp_path):
    """In shelf mode the whole shelf is already laid out, so a pull to a sibling book on the SAME
    shelf names a page the librarian can already see. Linking it would be noise."""
    fund = _pages_of(store, "ai/rag/rag-fundamentals")
    adv = _pages_of(store, "ai/rag/advanced-rag-techniques")
    placements = {p: (1.0, 0.0, 0.0) for p in fund} | {p: (0.0, 1.0, 0.0) for p in adv}
    placements[fund[0]] = (0.05, 1.0, 0.0)  # pulled toward a book on the SAME shelf

    cat = _catalog(store, tmp_path, placements)
    report = build_crosslinks(store, cat, min_delta=0.0)
    cat.close()
    assert report.written == 0 and report.skipped_same_shelf >= 1


def test_cross_domain_links_are_refused(store, tmp_path):
    """Two reasons (crosslinks.py): they are nearly always false positives, and — the serious one —
    the Retail domain is private and gitignored (D-020) while AI is tracked, so a link written on an
    AI book would carry a private page's title into a tracked file."""
    domain = store.create(ROOT_ID, "domain", "Retail", "private corpus")
    shelf = store.create(domain.id, "shelf", "KPIs", "")
    book = store.create(shelf.id, "book", "KPI Dictionary", "")
    # two pages: leave-one-out needs a "rest of the book" to compare the stray against
    anchor = store.write_page(book.id, "Gross Margin", "# Gross Margin\n\nsecret")
    private = store.write_page(book.id, "Sell Through", "# Sell Through\n\nalso secret")

    llm = _pages_of(store, "ai/llm/llm-foundations")
    placements = {p: (0.0, 1.0, 0.0) for p in llm}
    placements[anchor.id] = (1.0, 0.0, 0.0)  # where the Retail book really lives
    placements[private.id] = (0.05, 1.0, 0.0)  # …but this Retail page sits among the AI pages

    cat = _catalog(store, tmp_path, placements)
    report = build_crosslinks(store, cat, min_delta=0.0)
    cat.close()

    assert report.skipped_cross_domain >= 1
    assert report.written == 0
    assert not store.get(store.resolve_path("ai/llm/llm-foundations")).see_also


# ------------------------------------------------------------------ the walk can FOLLOW them


def test_the_librarian_can_read_a_cross_linked_page_from_another_shelf(store, tmp_path):
    """The whole point. A cross-reference the librarian cannot follow is decoration."""
    cat, stray = _planted(store, tmp_path)
    build_crosslinks(store, cat, min_delta=0.0, max_per_book=3)
    cat.close()
    stray_title = store.get(stray).title

    nav = Navigation(store, get_settings())
    nav.start_menu()
    nav.execute("browse", {"target": "AI"})
    nav.execute("browse", {"target": "LLM"})  # NOT the shelf the page lives on
    out = nav.execute("open_shelf", {})

    assert "Cross-references" in out.text
    assert stray_title in out.text
    assert "cross-refs" in out.event.detail

    read = nav.execute("read_page", {"title": stray_title})
    assert read.text.startswith("[PAGE")
    assert nav.state.pages_read == 1
    # …and the citation still reports the page's TRUE home, not the shelf it was reached from
    assert "RAG" in store.path_str(nav.state.pages[0].page_id)


def test_a_cross_reference_never_shadows_a_real_page_on_the_shelf(store, tmp_path):
    """If a linked page shares a title with a page that really is on this shelf, the real one wins —
    a cross-ref only ever ADDS reachable pages, it can never hide one."""
    cat, stray = _planted(store, tmp_path)
    build_crosslinks(store, cat, min_delta=0.0, max_per_book=3)
    cat.close()

    stray_title = store.get(stray).title
    llm_book = store.resolve_path("ai/llm/llm-foundations")
    twin = store.write_page(llm_book, stray_title, "# twin\n\nthe page that is really here")

    nav = Navigation(store, get_settings())
    nav.start_menu()
    nav.execute("browse", {"target": "AI"})
    nav.execute("browse", {"target": "LLM"})
    nav.execute("open_shelf", {})
    nav.execute("read_page", {"title": stray_title})

    assert nav.state.pages[0].page_id == twin.id  # the page that is actually on the shelf
