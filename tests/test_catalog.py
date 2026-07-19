"""Card-catalog tests (P2c) — storage, question generation, lookup, and the ask_librarian tool.

All LLM-free: storage uses hand-built unit vectors; question/embed calls go through fakes.
"""

import numpy as np
import pytest

from libkb import seed
from libkb.agent.tools import Navigation
from libkb.catalog.search import lookup
from libkb.catalog.store import Catalog
from libkb.config import get_settings
from libkb.ingest.questions import generate_questions, index_page
from libkb.library.store import LibraryStore
from libkb.llm.client import LLMResult, ToolCall

E = np.eye(3, dtype=np.float32)  # three orthonormal vectors


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


# ---------------------------------------------------------------- fakes


class FakeEmbedLLM:
    """Returns a fixed vector for every text (query or document)."""

    def __init__(self, vec):
        self.vec = np.asarray(vec, dtype=np.float32)

    def embed(self, texts, *, task="RETRIEVAL_DOCUMENT", model=None):
        return np.asarray([self.vec for _ in texts], dtype=np.float32)


class FakeIndexLLM:
    """load_prompt + generate_json (questions) + embed (one-hot per row)."""

    def __init__(self, payload, dim=3):
        self.payload = payload
        self.dim = dim

    def load_prompt(self, name, **kw):
        return name

    def generate_json(self, contents, *, schema, **kw):
        return self.payload

    def embed(self, texts, *, task="RETRIEVAL_DOCUMENT", model=None):
        arr = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i in range(len(texts)):
            arr[i, i % self.dim] = 1.0
        return arr


# ---------------------------------------------------------------- storage


def test_add_search_dedup_remove_clear(tmp_path):
    cat = Catalog(tmp_path / "catalog.db")
    # p1 has two questions, both pointing the same direction as E[0]
    cat.add_page(
        page_id="p1",
        book_id="b1",
        path="A ▸ p1",
        texts=["q1a", "q1b"],
        langs=["en", "vi"],
        embeddings=np.vstack([E[0], E[0]]),
    )
    cat.add_page(
        page_id="p2",
        book_id="b1",
        path="A ▸ p2",
        texts=["q2"],
        langs=["en"],
        embeddings=E[1:2],
    )
    assert cat.count() == 3
    assert cat.page_ids() == {"p1", "p2"}

    hits = cat.search(E[0], top_k=5)
    assert [h.page_id for h in hits] == ["p1", "p2"]  # distinct pages, best first
    assert hits[0].score == pytest.approx(1.0)
    assert hits[1].score == pytest.approx(0.0)

    assert cat.remove_page("p1") == 2
    assert cat.page_ids() == {"p2"}
    assert all(h.page_id != "p1" for h in cat.search(E[0], top_k=5))

    cat.clear()
    assert cat.count() == 0
    assert cat.search(E[0], top_k=5) == []


def test_search_empty_catalog(tmp_path):
    cat = Catalog(tmp_path / "catalog.db")
    assert cat.search(E[0], top_k=5) == []


def test_lookup_applies_threshold(tmp_path):
    cat = Catalog(tmp_path / "catalog.db")
    cat.add_page(
        page_id="p1",
        book_id="b1",
        path="A ▸ p1",
        texts=["q"],
        langs=["en"],
        embeddings=E[0:1],
    )
    # query aligned with E[0] → score 1.0, passes a high threshold
    assert lookup(cat, "q", llm=FakeEmbedLLM(E[0]), threshold=0.8)
    # query aligned with E[1] → score 0.0, filtered out
    assert lookup(cat, "q", llm=FakeEmbedLLM(E[1]), threshold=0.8) == []


def test_margin_gate_stays_quiet_when_two_pages_tie(tmp_path):
    """The real gate (D-028): if the runner-up page is just as close, say nothing and walk."""
    cat = Catalog(tmp_path / "catalog.db")
    for pid in ("p1", "p2"):  # both pages point the same way as the query
        cat.add_page(
            page_id=pid,
            book_id="b",
            path=f"A ▸ {pid}",
            texts=["q"],
            langs=["en"],
            embeddings=E[0:1],
        )
    assert lookup(cat, "q", llm=FakeEmbedLLM(E[0]), min_margin=0.05) == []


def test_margin_gate_fires_and_returns_only_the_winner(tmp_path):
    cat = Catalog(tmp_path / "catalog.db")
    cat.add_page(
        page_id="p1",
        book_id="b",
        path="A ▸ p1",
        texts=["q"],
        langs=["en"],
        embeddings=E[0:1],
    )
    cat.add_page(
        page_id="p2",
        book_id="b",
        path="A ▸ p2",
        texts=["q"],
        langs=["en"],
        embeddings=E[1:2],  # orthogonal → far behind
    )
    hits = lookup(cat, "q", llm=FakeEmbedLLM(E[0]), min_margin=0.05)
    assert [h.page_id for h in hits] == ["p1"]  # only the page it is confident about


def test_probe_reports_both_held_out_views(tmp_path):
    from libkb.evals.catalog_probe import probe

    cat = Catalog(tmp_path / "catalog.db")
    for i, pid in enumerate(("p1", "p2", "p3")):
        cat.add_page(
            page_id=pid,
            book_id="b",
            path=f"A ▸ {pid}",
            texts=["qa", "qb"],
            langs=["vi", "en"],
            embeddings=np.vstack([E[i % 3], E[i % 3]]),
        )
    results = probe(cat)
    assert [r.label[:3] for r in results] == ["LOO", "LOI"]
    assert all(r.n == 6 and r.by_margin and r.by_threshold for r in results)


# ---------------------------------------------------------------- questions


def test_generate_questions_expands_bilingual():
    payload = {
        "questions": [{"vi": "Câu một?", "en": "Question one?"}, {"vi": "Câu hai?", "en": "Q2?"}]
    }
    qs = generate_questions("Title", "body", llm=FakeIndexLLM(payload))
    assert [(q.text, q.lang) for q in qs] == [
        ("Câu một?", "vi"),
        ("Question one?", "en"),
        ("Câu hai?", "vi"),
        ("Q2?", "en"),
    ]


def test_card_supplies_the_furniture_a_source_did_not(tmp_path):
    """The ingest CONTRACT: a page whose source gave no spine label still gets one, from the same
    lite call that was generating its questions anyway. No source ever needs code."""
    from libkb.ingest.questions import generate_card

    payload = {
        "one_line": "  Compares HNSW and IVF on recall vs memory  ",
        "keywords": ["HNSW", "IVF", "recall", "a", "b", "c", "dropped"],
        "questions": [{"vi": "Câu?", "en": "Q?"}],
    }
    card = generate_card("T", "body", llm=FakeIndexLLM(payload))
    assert card.one_line == "Compares HNSW and IVF on recall vs memory"
    assert len(card.keywords) == 6  # capped
    assert card.questions


def test_index_page_writes_rows(tmp_path):
    cat = Catalog(tmp_path / "catalog.db")
    payload = {"questions": [{"vi": "Câu?", "en": "Q?"}]}
    card = index_page(
        cat,
        page_id="pg",
        book_id="bk",
        path="A ▸ B ▸ pg",
        title="T",
        markdown="body",
        llm=FakeIndexLLM(payload),
        index_kind="questions",
    )
    assert len(card.questions) == 2  # vi + en
    assert card.indexed_rows == 2
    assert cat.page_ids() == {"pg"}
    # re-indexing replaces rather than duplicates
    index_page(
        cat,
        page_id="pg",
        book_id="bk",
        path="A ▸ B ▸ pg",
        title="T",
        markdown="body2",
        llm=FakeIndexLLM(payload),
        index_kind="questions",
    )
    assert cat.count() == 2


def test_index_page_text_kind_makes_no_llm_call(tmp_path):
    """A text index embeds the page body and generates NOTHING — the whole economic case for it is
    that a real corpus cannot afford a generation call per page (D-039). One row, empty display
    text (the 8k body must never ride into a triage card), and generate_json is never reached."""
    cat = Catalog(tmp_path / "catalog.db")

    class BoomOnGenerate(FakeIndexLLM):
        def generate_json(self, contents, *, schema, **kw):
            raise AssertionError("text index must not call the model")

    card = index_page(
        cat,
        page_id="pg",
        book_id="bk",
        path="A ▸ B ▸ pg",
        title="Reranking",
        markdown="cross-encoders re-score candidate pages",
        llm=BoomOnGenerate({}),
        index_kind="text",
    )
    assert card.questions == []  # nothing generated
    assert card.indexed_rows == 1  # but the page IS in the sieve
    assert cat.count() == 1
    rows = cat.all_questions()
    assert [r["text"] for r in rows] == [""]  # display text empty; the vector holds the body


def test_index_page_both_kind_writes_questions_and_text(tmp_path):
    cat = Catalog(tmp_path / "catalog.db")
    payload = {"questions": [{"vi": "Câu?", "en": "Q?"}]}
    card = index_page(
        cat,
        page_id="pg",
        book_id="bk",
        path="A ▸ B ▸ pg",
        title="T",
        markdown="body",
        llm=FakeIndexLLM(payload),
        index_kind="both",
    )
    assert card.indexed_rows == 3  # vi + en + one text row
    assert cat.count() == 3


def test_catalog_refuses_mixed_index_kind(tmp_path):
    """A catalog holds ONE representation. Reindexing part of it a different way (questions here,
    text there) would make a page's rank depend on which reindex last touched it — metric bug 6.6,
    silent. The lock mirrors the embedder lock: mismatch raises, `--fresh` is the way out."""
    cat = Catalog(tmp_path / "catalog.db")
    index_page(
        cat,
        page_id="p1",
        book_id="bk",
        path="A ▸ p1",
        title="T",
        markdown="body",
        llm=FakeIndexLLM({"questions": [{"vi": "Câu?", "en": "Q?"}]}),
        index_kind="questions",
    )
    assert cat.index_kind() == "questions"
    with pytest.raises(ValueError, match="6.6"):
        index_page(
            cat,
            page_id="p2",
            book_id="bk",
            path="A ▸ p2",
            title="T2",
            markdown="body2",
            llm=FakeIndexLLM({}),
            index_kind="text",
        )
    # --fresh clears the marker, so the catalog can be rebuilt the new way
    cat.clear()
    assert cat.index_kind() is None
    index_page(
        cat,
        page_id="p2",
        book_id="bk",
        path="A ▸ p2",
        title="T2",
        markdown="body2",
        llm=FakeIndexLLM({}),
        index_kind="text",
    )
    assert cat.index_kind() == "text"


# ---------------------------------------------------------------- ask_librarian tool


def _seed_catalog_for_reranking(store, tmp_path):
    """Put the seed's reranking page into a catalog, aligned with E[0]."""
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


def test_ask_librarian_unavailable_without_catalog(store):
    nav = Navigation(store, get_settings())
    out = nav.execute("ask_librarian", {"query": "reranking"})
    assert "unavailable" in out.text.lower()
    assert nav.state.librarian_calls == 0


def test_ask_librarian_returns_and_budgets(store, tmp_path):
    cat = _seed_catalog_for_reranking(store, tmp_path)
    nav = Navigation(store, get_settings(), catalog=cat, llm=FakeEmbedLLM(E[0]))

    out = nav.execute("ask_librarian", {"query": "reranking"})
    assert "suggests" in out.text.lower()
    assert "Advanced RAG Techniques" in out.text
    assert nav.state.librarian_calls == 1

    # exhaust the budget (max_ask_librarian defaults to 2)
    for _ in range(get_settings().max_ask_librarian):
        out = nav.execute("ask_librarian", {"query": "reranking"})
    assert "budget reached" in out.text.lower()


def test_navigate_offers_ask_librarian_when_catalog_present(store, tmp_path):
    from libkb.agent.navigator import navigate

    cat = _seed_catalog_for_reranking(store, tmp_path)

    class CatalogWalkLLM(FakeEmbedLLM):
        def __init__(self, script, vec):
            super().__init__(vec)
            self._script = list(script)
            self.calls = 0

        def load_prompt(self, name, **kw):
            return f"[{name}]"

        def generate(self, contents, **kw):
            if self.calls < len(self._script):
                name, args = self._script[self.calls]
                self.calls += 1
                return LLMResult(text=None, tool_calls=[ToolCall(name=name, args=args)])
            self.calls += 1
            return LLMResult(text="", tool_calls=[ToolCall(name="not_found", args={"reason": "x"})])

    script = [
        ("ask_librarian", {"query": "reranking"}),
        ("browse", {"target": "AI"}),
        ("browse", {"target": "RAG"}),
        ("open_book", {"title": "Advanced RAG Techniques"}),
        ("read_page", {"title": "Reranking & Cross-encoders"}),
        ("found", {"note": "ok"}),
    ]
    result = navigate("reranking?", store=store, llm=CatalogWalkLLM(script, E[0]), catalog=cat)
    assert result.status == "FOUND"
    assert any(e.action == "ask" for e in result.events)


# ---------------------------------------------------------------- two providers, one vector space


def test_catalog_refuses_a_second_embedder(tmp_path):
    """Two embedders are two coordinate systems. A cosine across them is not a worse number — it is
    not a number, and nothing downstream would notice: search would return confident, ranked
    nonsense. The only failure we can neither measure nor debug is the silent one."""
    import numpy as np
    import pytest

    cat = Catalog(tmp_path / "catalog.db")
    vec = np.ones((1, 4), dtype=np.float32)
    cat.add_page(
        page_id="p1",
        book_id="b",
        path="A ▸ B ▸ p1",
        texts=["q"],
        langs=["en"],
        embeddings=vec,
        embed_model="gemini-embedding-001",
    )
    assert cat.embedder() == "gemini-embedding-001"

    with pytest.raises(ValueError, match="two vector spaces|vector spaces"):
        cat.add_page(
            page_id="p2",
            book_id="b",
            path="A ▸ B ▸ p2",
            texts=["q"],
            langs=["en"],
            embeddings=vec,
            embed_model="text-embedding-v4",
        )
    # …and `reindex --fresh` is the sanctioned way to change one
    cat.clear()
    assert cat.embedder() is None
    cat.add_page(
        page_id="p2",
        book_id="b",
        path="A ▸ B ▸ p2",
        texts=["q"],
        langs=["en"],
        embeddings=vec,
        embed_model="text-embedding-v4",
    )
    assert cat.embedder() == "text-embedding-v4"


def test_qwen_models_route_to_dashscope_and_refuse_tools():
    """The bulk tier may go to Qwen; NAVIGATION may not. D-027 measured a cheap model collapsing at
    exactly that job (page 54% vs 86%), and a tool loop that half-works is worse than one that
    refuses."""
    import pytest

    from libkb.exceptions import LLMError
    from libkb.llm.client import LLM, ToolSpec

    llm = LLM.__new__(LLM)  # no API client — we are only testing the routing rule
    llm._settings = get_settings()
    llm._dashscope = None

    assert llm._is_dashscope("qwen-flash")
    assert llm._is_dashscope("text-embedding-v4")
    assert not llm._is_dashscope("gemini-3.1-flash-lite")
    assert not llm._is_dashscope("gemini-embedding-001")

    spec = ToolSpec(name="t", description="d", parameters={"type": "object"})
    with pytest.raises(LLMError, match="Gemini-only"):
        llm.generate("hi", model="qwen-flash", tools=[spec])


def test_a_schema_is_a_request_not_a_guarantee():
    """Gemini enforces `response_schema` server-side; DashScope only honours `json_object` and
    leaves the shape to the model. Qwen periodically returned `"questions": ["…"]` — valid JSON,
    wrong shape — and `item.get(lang)` raised AttributeError. `index_page_safe` swallowed it per
    page, so **439 of 2,079 pages (21%) never entered the catalog** while the import printed a
    success line. The parser must bend, not break."""
    from libkb.ingest.questions import generate_card

    flat = {"one_line": "x", "questions": ["What is GMROI?", "How is it computed?"]}
    card = generate_card("T", "body", llm=FakeIndexLLM(flat))
    assert [q.text for q in card.questions] == ["What is GMROI?", "How is it computed?"]
    assert all(q.lang == "vi" for q in card.questions)  # first configured language

    junk = {"questions": [{"text": "Only a text key?"}, 42, None, {}]}
    card = generate_card("T", "body", llm=FakeIndexLLM(junk))
    assert [q.text for q in card.questions] == ["Only a text key?"]  # salvage what is there


def test_a_broken_call_fails_CLOSED_not_open():
    """P6's real enemy is not a confident lie — it is a broken call that gets dressed up as an
    answer. The old `generate_json` took a truncated `{"answer": "J` and asked the model to *fix
    this output*; the model obliged, inventing `"sufficient": true` around the fragment. MEASURED on
    301 unanswerable questions: **40 came back as a single character**. A malformed response must
    raise, so `answer_query_safe` can turn it into an honest NOT_FOUND."""
    import pytest

    from libkb.exceptions import LLMError
    from libkb.llm.client import LLM, LLMResult

    llm = LLM.__new__(LLM)
    llm._settings = get_settings()
    llm.default_model = None
    calls: list[str] = []

    def fake(contents, **kw):
        calls.append(str(contents)[:20])
        return LLMResult(text='"J"')  # valid JSON — and NOT the object we asked for

    llm.generate = fake
    schema = {"type": "object", "required": ["answer", "sufficient"]}
    with pytest.raises(LLMError, match="required keys"):
        llm.generate_json("what is X?", schema=schema)
    assert len(calls) == 2  # asked, re-ASKED (never "fix your fragment"), then raised
    assert calls[0] == calls[1]  # the retry re-sends the ORIGINAL question


def test_the_library_never_answers_with_one_character(tmp_path):
    """The second guard, at the place that decides whether the library speaks. Two characters is the
    shortest true thing it can say — MultiHop's comparison answers really are "Yes"/"No"."""
    from libkb.agent.answerer import compose_answer
    from libkb.library.models import PageContent

    class FakeLLM:
        def __init__(self, payload):
            self.payload = payload

        def load_prompt(self, name, **kw):
            return name

        def generate_json(self, contents, *, schema, **kw):
            return self.payload

    store = LibraryStore(tmp_path / "library")
    store.init_library()
    seed.apply(store)
    page_id = next(m.id for m in store.iter_subtree() if m.kind == "page")
    page = store.page(page_id)
    pages = [PageContent(page_id=page_id, book_id=page.book_id, title="T", markdown="body")]

    junk = compose_answer("q", pages, store, llm=FakeLLM({"answer": "J", "sufficient": True}))
    assert junk.status == "not_found"  # a fragment is not an answer, whatever the model claims

    real = compose_answer("q", pages, store, llm=FakeLLM({"answer": "Yes", "sufficient": True}))
    assert real.status == "answered"  # …but "Yes" is a complete answer and must survive


def test_confidence_gate_is_separate_from_the_basket(tmp_path):
    """D-043: the answerer's OWN confidence is a knob distinct from how many pages the basket holds.
    A `sufficient` answer the model can only back at `low` confidence stays silent when the caller
    demands `medium` — this is what lets the basket widen for accuracy without honesty falling."""
    from libkb.agent.answerer import compose_answer
    from libkb.library.models import PageContent

    class FakeLLM:
        def __init__(self, payload):
            self.payload = payload

        def load_prompt(self, name, **kw):
            return name

        def generate_json(self, contents, *, schema, **kw):
            return self.payload

    store = LibraryStore(tmp_path / "library")
    store.init_library()
    seed.apply(store)
    page_id = next(m.id for m in store.iter_subtree() if m.kind == "page")
    page = store.page(page_id)
    pages = [PageContent(page_id=page_id, book_id=page.book_id, title="T", markdown="body")]
    low = {"answer": "A real sentence.", "confidence": "low", "sufficient": True}

    # gate OFF (default "low") — a low-confidence but sufficient answer is served
    assert (
        compose_answer("q", pages, store, llm=FakeLLM(low), min_confidence="low").status
        == "answered"
    )
    # gate at "medium" — the same answer is now an honest NOT_FOUND
    assert (
        compose_answer("q", pages, store, llm=FakeLLM(low), min_confidence="medium").status
        == "not_found"
    )
    # a high-confidence answer clears even the strictest floor
    high = {"answer": "A real sentence.", "confidence": "high", "sufficient": True}
    assert (
        compose_answer("q", pages, store, llm=FakeLLM(high), min_confidence="high").status
        == "answered"
    )
