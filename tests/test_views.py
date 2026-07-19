"""Materialized-view rebuild tests (P1/D-004), incl. the P3 extension of rebuilding BOOK
descriptions from their pages. LLM-free via a fake that records the prompt vars."""

import pytest

from libkb import seed
from libkb.config import get_settings
from libkb.library.store import LibraryStore
from libkb.library.views import rebuild_all, rebuild_description
from libkb.llm.client import LLMResult


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


class FakeViewLLM:
    def __init__(self, text="DISCRIMINATIVE DESC"):
        self.text = text
        self.prompts = []

    def load_prompt(self, name, **kw):
        self.prompts.append(kw)
        return name

    def generate(self, contents, **kw):
        return LLMResult(text=self.text)


def test_rebuild_book_description_from_its_pages(store):
    book_id = store.resolve_path("ai/rag/advanced-rag-techniques")
    fake = FakeViewLLM("Covers reranking and hybrid search; not fundamentals.")

    out = rebuild_description(store, book_id, llm=fake)

    assert out and out == store.get(book_id).description
    kw = fake.prompts[-1]
    assert kw["kind"] == "book"
    assert "Reranking" in kw["children"]  # the book's pages are the source
    assert kw["siblings"] != "(none)"  # sibling books provide the discrimination context


def test_rebuild_skips_leaf_pages(store):
    book_id = store.resolve_path("ai/rag/advanced-rag-techniques")
    page = next(c for c in store.children(book_id) if c.kind == "page")
    assert rebuild_description(store, page.id, llm=FakeViewLLM()) is None


def test_rebuild_all_now_covers_books(store):
    fake = FakeViewLLM("x")
    report = rebuild_all(store, llm=fake)
    kinds = {store.get(nid).kind for nid in report.touched}
    assert {"domain", "shelf", "book"} <= kinds
