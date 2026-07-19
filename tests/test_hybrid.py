"""Hybrid retrieval: BM25 covers what embeddings structurally miss (§7.3). LLM-free.

Dense retrieval has a known blind spot — rare terms and named entities. "GMROI", "HNSW", a SKU
code, a Japanese retail term: an embedding smears them into whatever neighbourhood it learned at
training time, because it never really learned them. BM25 matches them exactly.

Fusion is by RANK (reciprocal rank fusion), never by score. Cosines here crowd into 0.87–0.90
(D-028) and BM25 lives on an unrelated scale — a weighted-sum fusion would be calibrating noise.
"""

import numpy as np
import pytest

from libkb.catalog.db import connect, has_fts
from libkb.catalog.search import hybrid_lookup
from libkb.catalog.store import Catalog, _fts_terms
from libkb.config import get_settings


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _unit(*values):
    v = np.asarray([values], dtype=np.float32)
    return v / np.linalg.norm(v)


class BlindEmbedder:
    """An embedder that has never seen the rare term: it puts the query nowhere near the page that
    actually contains it. Exactly the failure BM25 exists to cover."""

    def __init__(self, query_vec):
        self._q = query_vec

    def embed(self, texts, *, task="RETRIEVAL_DOCUMENT", model=None):
        return self._q


@pytest.fixture
def catalog(tmp_path):
    cat = Catalog(tmp_path / "catalog.db")
    # the page that really answers "what is GMROI?" — but the embedder does not know the word
    cat.add_page(
        page_id="p_gmroi",
        book_id="b1",
        path="Retail ▸ KPIs ▸ Dictionary ▸ GMROI",
        texts=["How is GMROI calculated for a category?"],
        langs=["en"],
        embeddings=_unit(1.0, 0.0, 0.0),
    )
    # a page about generic profitability — semantically close to the query, lexically irrelevant
    cat.add_page(
        page_id="p_margin",
        book_id="b1",
        path="Retail ▸ KPIs ▸ Dictionary ▸ Margin",
        texts=["How do I improve product profitability and margin?"],
        langs=["en"],
        embeddings=_unit(0.0, 1.0, 0.0),
    )
    yield cat
    cat.close()


def test_fts_terms_never_hands_raw_text_to_match():
    """A reader's sentence is not a query language. Quotes, `*`, and the words AND/OR/NOT/NEAR are
    FTS5 operators — passed raw, a question is a syntax error at best and a different query at
    worst."""
    quoted = '"what" OR "is" OR "GMROI" OR "AND" OR "margin"'
    assert _fts_terms('what is "GMROI" AND margin*') == quoted
    assert _fts_terms("?") == ""  # nothing usable — the caller must fall back to dense


def test_lexical_finds_the_rare_term_the_embedder_missed(catalog, tmp_path):
    if not has_fts(connect(tmp_path / "catalog.db")):
        pytest.skip("this SQLite has no FTS5 build")

    hits = catalog.search_lexical("what is GMROI?", top_k=5)
    assert hits and hits[0].page_id == "p_gmroi"


def test_hybrid_rescues_a_page_dense_ranked_second(catalog, tmp_path):
    if not has_fts(connect(tmp_path / "catalog.db")):
        pytest.skip("this SQLite has no FTS5 build")

    # the embedder is blind to "GMROI": it puts the query on the *margin* page's axis
    blind = BlindEmbedder(_unit(0.0, 1.0, 0.0))

    dense_only = catalog.search(_unit(0.0, 1.0, 0.0)[0], top_k=2)
    assert dense_only[0].page_id == "p_margin"  # dense alone gets it WRONG

    fused = hybrid_lookup(catalog, "what is GMROI?", llm=blind, top_k=2)
    assert fused[0].page_id == "p_gmroi"  # …lexical drags the right page back to the top


def test_hybrid_degrades_to_dense_when_the_query_has_no_usable_terms(catalog):
    blind = BlindEmbedder(_unit(0.0, 1.0, 0.0))
    fused = hybrid_lookup(catalog, "?", llm=blind, top_k=2)
    assert [h.page_id for h in fused] == ["p_margin", "p_gmroi"]  # pure dense order, no crash


def test_the_lexical_index_stays_in_sync_when_a_page_is_reindexed(catalog, tmp_path):
    if not has_fts(connect(tmp_path / "catalog.db")):
        pytest.skip("this SQLite has no FTS5 build")

    catalog.remove_page("p_gmroi")
    assert catalog.search_lexical("GMROI", top_k=5) == []  # the delete trigger fired

    catalog.add_page(
        page_id="p_gmroi",
        book_id="b1",
        path="Retail ▸ KPIs ▸ Dictionary ▸ GMROI",
        texts=["GMROI again"],
        langs=["en"],
        embeddings=_unit(1.0, 0.0, 0.0),
    )
    assert [h.page_id for h in catalog.search_lexical("GMROI", top_k=5)] == ["p_gmroi"]


def test_within_restricts_the_lexical_ranking_too(catalog, tmp_path):
    if not has_fts(connect(tmp_path / "catalog.db")):
        pytest.skip("this SQLite has no FTS5 build")

    # the shelf shortlist ranks only the pages on the shelf it is standing on
    assert catalog.search_lexical("GMROI", top_k=5, within={"p_margin"}) == []
