"""Orchestrator catalog-shortcut tests (P2c) — LLM-free via a fake that fails if a walk starts."""

import numpy as np
import pytest

from libkb import seed
from libkb.agent.orchestrator import _try_shortcut, answer_query, answer_query_safe
from libkb.catalog.store import Catalog
from libkb.config import get_settings
from libkb.library.store import LibraryStore

E = np.eye(3, dtype=np.float32)


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


@pytest.fixture
def catalog(store, tmp_path):
    cat = Catalog(tmp_path / "catalog.db")
    book_id = store.resolve_path("ai/rag/advanced-rag-techniques")
    page = next(c for c in store.children(book_id) if c.kind == "page")
    cat.add_page(
        page_id=page.id,
        book_id=book_id,
        path=store.path_str(page.id),
        texts=["how does reranking work?"],
        langs=["en"],
        embeddings=E[0:1],
    )
    return cat


class ShortcutLLM:
    """Matches every query to E[0]; answers with a fixed sufficiency verdict; never walks."""

    def __init__(self, vec, sufficient=True):
        self.vec = np.asarray(vec, dtype=np.float32)
        self.sufficient = sufficient

    def load_prompt(self, name, **kw):
        return f"[{name}]"

    def embed(self, texts, *, task="RETRIEVAL_DOCUMENT", model=None):
        return np.asarray([self.vec for _ in texts], dtype=np.float32)

    def generate_json(self, contents, *, schema, **kw):
        return {
            "answer": "Reranking reorders candidates.",
            "confidence": "high",
            "sufficient": self.sufficient,
        }

    def generate(self, contents, **kw):
        raise AssertionError("the walk must not run when the shortcut answers")


def test_shortcut_answers_without_walking(store, catalog):
    result = answer_query("what is reranking?", store=store, catalog=catalog, llm=ShortcutLLM(E[0]))
    assert result.answer.status == "answered"
    assert result.nav.reason == "card-catalog shortcut"
    assert result.nav.hops == 0
    assert result.nav.pages  # answered from a real page


def test_shortcut_skipped_below_threshold(store, catalog):
    # query aligned with E[1] → cosine 0 with the stored E[0] row → no hit passes the threshold
    out = _try_shortcut("x", store, catalog, ShortcutLLM(E[1]), get_settings(), None)
    assert out is None


def test_shortcut_skipped_when_evidence_insufficient(store, catalog):
    out = _try_shortcut(
        "x", store, catalog, ShortcutLLM(E[0], sufficient=False), get_settings(), None
    )
    assert out is None


def test_safe_fails_closed_on_an_unexpected_bug_not_just_llmerror(store, catalog):
    """P6: any failure to answer is an honest NOT_FOUND, never a 500. `answer_query_safe` caught
    only LLMError, so a bare TypeError (a malformed response slipping a None past a guard, seen at
    ~0.5% under a concurrent eval) would crash a request. Now anything unexpected fails closed."""

    class BoomLLM(ShortcutLLM):
        def embed(self, texts, *, task="RETRIEVAL_DOCUMENT", model=None):
            raise TypeError("'NoneType' object is not subscriptable")

    result = answer_query_safe(
        "what is reranking?", store=store, catalog=catalog, llm=BoomLLM(E[0])
    )
    assert result.answer.status == "not_found"  # closed, not crashed
    assert result.nav.status == "NOT_FOUND"
