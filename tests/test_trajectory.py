"""The demand-side flywheel (§8.4) and the evolving query (§8.3). LLM-free.

The founding worry — *can ingest-time generated questions ever be enough?* — has a measured answer:
no. On an intent the generator never anticipated, the catalog's top-1 is 39.3%. They were never
meant to be enough; they are the cold start. The library's real memory is the questions it has
actually been asked, and that memory can only be learned from traffic.
"""

import numpy as np
import pytest

from libkb import seed
from libkb.agent.tools import Navigation
from libkb.catalog.store import Catalog
from libkb.config import get_settings
from libkb.library.store import LibraryStore
from libkb.llm.client import LLMResult, ToolCall
from libkb.trajectory.harvest import harvest
from libkb.trajectory.store import Trajectory, TrajectoryStore


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
        return f"[{name}]"

    def embed(self, texts, *, task="RETRIEVAL_DOCUMENT", model=None):
        v = np.ones((len(texts), 3), dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    def generate(self, contents, **kwargs):
        if self.calls < len(self._script):
            name, args = self._script[self.calls]
            self.calls += 1
            return LLMResult(text=None, tool_calls=[ToolCall(name=name, args=args)])
        self.calls += 1
        return LLMResult(text="", tool_calls=[ToolCall(name="not_found", args={"reason": "end"})])


# ---------------------------------------------------------------- §8.3 reframe


def _at_rag_shelf(store, query):
    nav = Navigation(store, get_settings(), query=query)
    nav.start_menu()
    nav.execute("browse", {"target": "AI"})
    nav.execute("browse", {"target": "RAG"})
    return nav


def test_reframe_replaces_the_query_the_shortlist_searches_with(store):
    """Bates (1989): a real search is berrypicking — the query is rewritten with the vocabulary just
    learned. The system used to freeze the reader's words at t=0 and never revise them."""
    nav = _at_rag_shelf(store, "why are my results bad?")
    out = nav.execute(
        "reframe", {"new_query": "cross-encoder reranking", "why": "the shelf calls it reranking"}
    )

    assert nav.query == "cross-encoder reranking"
    assert nav.state.reframed_from == ["why are my results bad?"]
    assert "Restated" in out.text
    assert out.event.action == "reframe"
    assert out.event.snippet == "why are my results bad?"  # the pair, for the entry vocabulary


def test_reframing_costs_no_hop_because_rewording_is_not_travel(store):
    nav = _at_rag_shelf(store, "q")
    before = nav.state.hops
    nav.execute("reframe", {"new_query": "better words", "why": "learned them"})
    assert nav.state.hops == before


def test_reframe_is_budgeted_in_code(store, monkeypatch):
    """A librarian who keeps restating the question is lost, not learning.

    D-008: budgets live in code, never in prompts.
    """
    monkeypatch.setenv("LIBKB_MAX_REFRAMES", "1")
    get_settings.cache_clear()
    nav = _at_rag_shelf(store, "q")
    nav.execute("reframe", {"new_query": "second", "why": "x"})
    out = nav.execute("reframe", {"new_query": "third", "why": "y"})

    assert "budget reached" in out.text
    assert nav.query == "second"  # the over-budget call changed nothing


# ---------------------------------------------------------------- §8.4 the log


def test_a_walk_is_recorded_with_the_route_it_took(store, tmp_path, monkeypatch):
    monkeypatch.setenv("LIBKB_DB_PATH", str(tmp_path / "catalog.db"))
    monkeypatch.setenv("LIBKB_LIBRARY_DIR", str(store.root_dir))
    get_settings.cache_clear()

    from libkb.agent.orchestrator import answer_query

    llm = ScriptLLM(
        [
            ("browse", {"target": "AI"}),
            ("browse", {"target": "RAG"}),
            ("open_shelf", {}),
            ("read_page", {"title": "Reranking & Cross-encoders"}),
            ("found", {"note": "here"}),
        ]
    )
    llm.generate_json = lambda *a, **kw: {
        "answer": "Use a cross-encoder.",
        "confidence": "high",
        "sufficient": True,
    }
    answer_query("how do I rerank?", store=store, llm=llm, use_catalog=False)

    traj = TrajectoryStore(tmp_path / "catalog.db")
    [logged] = traj.harvestable()
    assert logged.query == "how do I rerank?"
    assert logged.status == "answered"
    assert len(logged.page_ids) == 1
    assert [e["action"] for e in logged.route] == ["enter", "enter", "shelf", "read", "found"]
    traj.close()


def test_logging_never_costs_the_reader_an_answer(store, tmp_path, monkeypatch):
    """Best-effort by design: the flywheel is valuable, but not more valuable than the answer."""
    from libkb.agent import orchestrator
    from libkb.trajectory import store as traj_store

    def explode(*a, **kw):
        raise OSError("the disk is on fire")

    monkeypatch.setattr(traj_store.TrajectoryStore, "__init__", explode)
    get_settings.cache_clear()

    llm = ScriptLLM([("not_found", {"reason": "nope"})])
    result = orchestrator.answer_query("anything", store=store, llm=llm, use_catalog=False)
    assert result.answer.status == "not_found"  # the reader still got a real, honest answer


def test_harvest_indexes_real_questions_as_catalog_rows(store, tmp_path):
    traj = TrajectoryStore(tmp_path / "catalog.db")
    cat = Catalog(tmp_path / "catalog.db")
    book = store.resolve_path("ai/rag/advanced-rag-techniques")
    page = next(c for c in store.children(book) if c.kind == "page")

    traj.record(Trajectory(query="làm sao xếp lại kết quả?", status="answered", page_ids=[page.id]))
    taken = harvest(traj, cat, store, llm=ScriptLLM([]))

    assert taken == [("làm sao xếp lại kết quả?", store.path_str(page.id))]
    assert cat.count() == 1
    assert traj.harvestable() == []  # harvested once, never again
    traj.close()
    cat.close()


def test_only_clean_labels_are_harvested(store, tmp_path):
    """A question answered from three pages does not tell us WHICH page it is about, and a
    not-found teaches nothing. A mislabelled row is worse than a missing one."""
    traj = TrajectoryStore(tmp_path / "catalog.db")
    traj.record(Trajectory(query="a", status="answered", page_ids=["p1", "p2", "p3"]))
    traj.record(Trajectory(query="b", status="not_found", page_ids=[]))
    traj.record(Trajectory(query="c", status="answered", page_ids=["p1"]))

    assert [t.query for t in traj.harvestable()] == ["c"]
    assert [t.query for t in traj.failures()] == ["b"]
    traj.close()
