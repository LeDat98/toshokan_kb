"""The Observatory endpoint helper: real KPIs + the trajectories feed, computed from logged traffic.

LLM-free. The learning-loop panels (eval history, misroutes, suggested fixes) are DELIBERATELY not
served — they need trajectory/analyzer.py, which is not built — so nothing here fabricates them.
"""

from __future__ import annotations

import pytest

from libkb.api.routes import _observatory, _traj_replay
from libkb.config import get_settings
from libkb.trajectory.store import Trajectory, TrajectoryStore


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A trajectory db wired to the settings db_path the endpoint reads."""
    path = tmp_path / "catalog.db"
    monkeypatch.setenv("LIBKB_DB_PATH", str(path))
    get_settings.cache_clear()
    return path


def test_empty_when_there_is_no_db(monkeypatch, tmp_path):
    monkeypatch.setenv("LIBKB_DB_PATH", str(tmp_path / "nope" / "catalog.db"))
    get_settings.cache_clear()
    out = _observatory()
    assert out["available"] is False
    assert out["kpis"] == [] and out["trajectories"] == []


def test_empty_when_db_exists_but_has_no_traffic(db):
    TrajectoryStore(db).close()  # creates the file, records nothing
    out = _observatory()
    assert out["available"] is False


def test_kpis_are_computed_from_real_traffic(db):
    traj = TrajectoryStore(db)
    traj.record(Trajectory(query="a", status="answered", reason="cascade", hops=2))
    traj.record(Trajectory(query="b", status="answered", reason="synthesize", hops=9))
    traj.record(Trajectory(query="c", status="not_found", reason="cascade"))
    traj.record(Trajectory(query="d", status="answered", reason="walk", hops=4))
    traj.close()

    out = _observatory()
    assert out["available"] is True
    kpis = {k["label"]: k["value"] for k in out["kpis"]}
    assert kpis["Queries logged"] == "4"
    assert kpis["Answer rate"] == "75%"  # 3 of 4
    assert kpis["Honest NOT_FOUND"] == "25%"
    assert kpis["Avg hops"] == "5.0"  # (2 + 9 + 4) / 3 over the answered rows


def test_feed_maps_reason_to_type_and_status_to_outcome(db):
    traj = TrajectoryStore(db)
    traj.record(Trajectory(query="lookup one", status="answered", reason="cascade"))
    traj.record(Trajectory(query="survey", status="answered", reason="synthesize"))
    traj.record(Trajectory(query="walked", status="not_found", reason="walk"))
    traj.close()

    rows = {r["query"]: r for r in _observatory()["trajectories"]}
    assert rows["lookup one"]["type"] == "Lookup"
    assert rows["survey"]["type"] == "Synthesis"
    assert rows["walked"]["type"] == "Explore"
    assert rows["survey"]["outcome"] == "FOUND"
    assert rows["walked"]["outcome"] == "NOT_FOUND"


def test_replay_keeps_only_node_steps():
    route = [
        {"action": "lookup", "title": "card catalog", "kind": None, "node_id": None},
        {"action": "browse", "title": "AI", "kind": "domain", "node_id": "d1"},
        {"action": "back", "title": "LLM", "kind": "shelf", "node_id": "s1"},
        {"action": "triage", "title": "p.12 Reranking", "kind": "page", "node_id": "p12"},
        {"action": "thought", "title": "hmm", "kind": None, "node_id": None},
    ]
    steps = _traj_replay(route)
    assert [s["kind"] for s in steps] == ["domain", "shelf", "page"]  # process-only events dropped
    assert [s["state"] for s in steps] == ["done", "back", "read"]


def test_synthesis_row_has_no_node_walk_to_replay(db):
    # a synthesize trajectory logs lookup/read/thought/compose/found — none carry a node kind
    traj = TrajectoryStore(db)
    traj.record(
        Trajectory(
            query="trends across the library",
            status="answered",
            reason="synthesize",
            route=[
                {"action": "lookup", "title": "card catalog", "kind": None, "node_id": None},
                {"action": "read", "title": "reading across N", "kind": None, "node_id": None},
                {"action": "found", "title": "FOUND", "kind": None, "node_id": None},
            ],
        )
    )
    traj.close()
    [row] = _observatory()["trajectories"]
    assert row["replay"] == []  # honest: a synthesis has no tree-walk to replay