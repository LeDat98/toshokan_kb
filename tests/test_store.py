import pytest

from libkb.exceptions import InvalidParent, NodeNotFound, SlugCollision
from libkb.library.models import ROOT_ID, UNCATALOGUED_ID
from libkb.library.store import LibraryStore


@pytest.fixture
def store(tmp_path):
    s = LibraryStore(tmp_path / "library")
    s.init_library()
    return s


@pytest.fixture
def small_tree(store):
    domain = store.create(ROOT_ID, "domain", "AI", "Artificial intelligence.")
    shelf = store.create(domain.id, "shelf", "RAG", "Retrieval-augmented generation.")
    book = store.create(shelf.id, "book", "RAG Fundamentals", "Intro to RAG.")
    return store, domain, shelf, book


def test_init_is_idempotent(store):
    store.init_library()
    root = store.get(ROOT_ID)
    assert root.kind == "root"


def test_root_menu_contains_uncatalogued(store):
    titles = [c.title for c in store.children(ROOT_ID)]
    assert "Uncatalogued" in titles


def test_create_hierarchy_and_path(small_tree):
    store, _, _, book = small_tree
    assert store.path_str(book.id) == "AI ▸ RAG ▸ RAG Fundamentals"
    refs = store.path_of(book.id)
    assert [r.kind for r in refs] == ["root", "domain", "shelf", "book"]


def test_invalid_parent_rejected(small_tree):
    store, domain, _, book = small_tree
    with pytest.raises(InvalidParent):
        store.create(domain.id, "book", "Misplaced")  # book directly under domain
    with pytest.raises(InvalidParent):
        store.create(book.id, "page", "Nope")  # pages go through write_page


def test_slug_collision_rejected(small_tree):
    store, _, shelf, _ = small_tree
    with pytest.raises(SlugCollision):
        store.create(shelf.id, "book", "RAG Fundamentals")


def test_nested_shelves_allowed(small_tree):
    store, _, shelf, _ = small_tree
    sub = store.create(shelf.id, "shelf", "Evaluation", "RAG eval sub-shelf.")
    assert store.path_str(sub.id) == "AI ▸ RAG ▸ Evaluation"


def test_page_roundtrip_with_colon_title(small_tree):
    store, _, _, book = small_tree
    page = store.write_page(
        book.id,
        "Hybrid Search: BM25 + Dense",
        "Body **markdown** here.",
        one_line="lexical + semantic",
        keywords=["bm25", "hybrid"],
        source_ref="seed",
    )
    content = store.page(page.id)
    assert content.title == "Hybrid Search: BM25 + Dense"
    assert content.markdown == "Body **markdown** here."
    assert content.source_ref == "seed"
    assert content.book_id == book.id


def test_children_of_book_follow_toc_order(small_tree):
    store, _, _, book = small_tree
    store.write_page(book.id, "Zeta topic", "z")
    store.write_page(book.id, "Alpha topic", "a")
    cards = store.children(book.id)
    assert [c.title for c in cards] == ["Zeta topic", "Alpha topic"]  # TOC order, not alphabetical
    assert all(c.kind == "page" for c in cards)


def test_menu_card_truncates_long_description(store):
    long_description = "x" * 500
    domain = store.create(ROOT_ID, "domain", "Verbose", long_description)
    card = next(c for c in store.children(ROOT_ID) if c.id == domain.id)
    assert len(card.one_line) <= 160
    assert card.one_line.endswith("…")


def test_recompute_stats(small_tree):
    store, domain, shelf, book = small_tree
    store.write_page(book.id, "P1", "one")
    store.write_page(book.id, "P2", "two")
    stats = store.recompute_stats(ROOT_ID)
    assert (stats.n_books, stats.n_pages) == (1, 2)
    assert stats.n_shelves == 2  # RAG + Uncatalogued
    assert store.get(domain.id).stats.n_books == 1
    assert store.get(shelf.id).stats.n_pages == 2


def test_resolve_path(small_tree):
    store, _, _, book = small_tree
    assert store.resolve_path("ai/rag/rag-fundamentals") == book.id
    assert store.resolve_path("uncatalogued") == UNCATALOGUED_ID
    with pytest.raises(NodeNotFound):
        store.resolve_path("ai/nonexistent")


def test_set_description_bumps_rev(small_tree):
    store, _, shelf, _ = small_tree
    store.set_description(shelf.id, "New regenerated description.", rev=2)
    meta = store.get(shelf.id)
    assert meta.description == "New regenerated description."
    assert meta.description_rev == 2


def test_see_also_rendered_on_card(small_tree):
    store, domain, shelf, _ = small_tree
    other = store.create(domain.id, "shelf", "LLM", "Language models.")
    store.add_see_also(shelf.id, other.id, "for prompting")
    card = next(c for c in store.children(domain.id) if c.id == shelf.id)
    assert card.see_also == ["for prompting — see: LLM"]


def test_move_keeps_id(small_tree):
    store, domain, _, book = small_tree
    other_shelf = store.create(domain.id, "shelf", "Archive", "Old material.")
    store.move(book.id, other_shelf.id)
    assert store.get(book.id).parent_id == other_shelf.id
    assert store.path_str(book.id) == "AI ▸ Archive ▸ RAG Fundamentals"


def test_index_survives_reopen(small_tree, tmp_path):
    store, _, _, book = small_tree
    store.write_page(book.id, "Persistent page", "content survives")
    reopened = LibraryStore(tmp_path / "library")
    assert reopened.get(book.id).title == "RAG Fundamentals"
    page_cards = reopened.children(book.id)
    assert page_cards and reopened.page(page_cards[0].id).markdown == "content survives"
