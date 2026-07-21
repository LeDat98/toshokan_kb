"""The library's real memory: what it was actually asked (ROUTING_REDESIGN §8.4).

The question the user asked at the very start of this work — *can ingest-time generated questions
ever be enough?* — has a measured answer: **no.** On an intent the generator never anticipated, the
catalog's top-1 is 39.3% (`libkb probe-recall`). They were never supposed to be enough. **They are
the cold start.**

An expert librarian's edge is not that they memorised the collection. It is that **they remember the
questions.** The current flywheel spins on *content* (page → guessed questions). This one spins on
*behaviour* (question → route → outcome → better route). Only the second one compounds, because real
query distributions are Zipf-shaped: you never cover the infinite tail, but the head is small, and
the head can only be learned from traffic.

Three things a trajectory is worth:
  - a SUCCESSFUL walk is a **real question → real page** pair, and can be indexed into the catalog
    exactly like a generated one — except it is not a guess;
  - a successful walk is also a **pathfinder**: a curated route for a recurring question, replayed
    as a hint (never a gate — §7.4);
  - a FAILED walk names the description that lied, which is a work item for view regeneration.

Storage is the same SQLite file as the catalog (D-002): regenerable, gitignored, and it must never
leak into the tracked tree.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog

from libkb.catalog.db import connect

log = structlog.get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS trajectories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query       TEXT NOT NULL,
    status      TEXT NOT NULL,           -- answered | not_found
    confidence  TEXT NOT NULL DEFAULT '',
    page_ids    TEXT NOT NULL DEFAULT '[]',   -- the pages the answer was actually built from
    path        TEXT NOT NULL DEFAULT '',     -- citation path of the first cited page
    hops        INTEGER NOT NULL DEFAULT 0,
    backtracks  INTEGER NOT NULL DEFAULT 0,
    route       TEXT NOT NULL DEFAULT '[]',   -- the walk, as [{action,title,kind,node_id}]
    reason      TEXT NOT NULL DEFAULT '',     -- which path answered: cascade|synthesize|walk|...
    indexed     INTEGER NOT NULL DEFAULT 0,   -- has this been fed back into the catalog?
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_traj_status ON trajectories(status);
CREATE INDEX IF NOT EXISTS idx_traj_indexed ON trajectories(indexed);
"""

# Columns added after the table first shipped. A warm db predates them, and CREATE TABLE IF NOT
# EXISTS will not add a column to an existing table — so each is ALTERed in idempotently on open.
_MIGRATIONS = ("ALTER TABLE trajectories ADD COLUMN reason TEXT NOT NULL DEFAULT ''",)


@dataclass
class Trajectory:
    query: str
    status: str
    confidence: str = ""
    page_ids: list[str] = field(default_factory=list)
    path: str = ""
    hops: int = 0
    backtracks: int = 0
    route: list[dict] = field(default_factory=list)
    reason: str = ""  # which path answered — cascade|synthesize|walk|concierge|calculator|…
    id: int | None = None
    indexed: bool = False
    created_at: str = ""  # ISO timestamp; read-only (record() stamps it)


class TrajectoryStore:
    def __init__(self, db_path: Path | str) -> None:
        self._conn = connect(db_path)  # same db as the catalog; connect() is idempotent
        self._conn.executescript(SCHEMA)
        for sql in _MIGRATIONS:
            # column already present on a fresh db (SCHEMA created it) → the ALTER errors; ignore
            with contextlib.suppress(Exception):
                self._conn.execute(sql)
        self._conn.commit()

    def record(self, traj: Trajectory) -> int:
        cur = self._conn.execute(
            "INSERT INTO trajectories "
            "(query, status, confidence, page_ids, path, hops, backtracks, route, reason, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                traj.query,
                traj.status,
                traj.confidence,
                json.dumps(traj.page_ids),
                traj.path,
                traj.hops,
                traj.backtracks,
                json.dumps(traj.route, ensure_ascii=False),
                traj.reason,
                datetime.now(UTC).isoformat(),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid or 0)

    def count(self, *, status: str | None = None) -> int:
        if status:
            row = self._conn.execute(
                "SELECT count(*) FROM trajectories WHERE status = ?", (status,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT count(*) FROM trajectories").fetchone()
        return int(row[0])

    def harvestable(self, *, limit: int = 100) -> list[Trajectory]:
        """Answered walks that landed on exactly one page and have not been fed back yet.

        One page, deliberately: a question answered from three pages does not tell us *which* page
        the question is about, so it is not a clean (question → page) label. Feeding it in would
        teach the catalog a route we cannot vouch for.
        """
        rows = self._conn.execute(
            "SELECT * FROM trajectories WHERE status = 'answered' AND indexed = 0 "
            "ORDER BY id LIMIT ?",
            (limit * 4,),
        ).fetchall()
        out = []
        for row in rows:
            page_ids = json.loads(row["page_ids"])
            if len(page_ids) != 1:
                continue
            out.append(_of(row))
            if len(out) >= limit:
                break
        return out

    def failures(self, *, limit: int = 50) -> list[Trajectory]:
        """Walks that found nothing. Each one names a description that lied, or a real gap."""
        rows = self._conn.execute(
            "SELECT * FROM trajectories WHERE status != 'answered' ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_of(r) for r in rows]

    def recent(self, *, limit: int = 50) -> list[Trajectory]:
        """The most recent trajectories of ANY status, newest first — the Observatory's feed."""
        rows = self._conn.execute(
            "SELECT * FROM trajectories ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_of(r) for r in rows]

    def status_counts(self) -> dict[str, int]:
        """{status: count} across the whole table — the denominator for the Observatory KPIs."""
        rows = self._conn.execute(
            "SELECT status, count(*) AS n FROM trajectories GROUP BY status"
        ).fetchall()
        return {row["status"]: int(row["n"]) for row in rows}

    def mark_indexed(self, ids: list[int]) -> None:
        self._conn.executemany(
            "UPDATE trajectories SET indexed = 1 WHERE id = ?", [(i,) for i in ids]
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _of(row) -> Trajectory:
    keys = row.keys()  # `reason`/`created_at` are absent on a db opened before the migration ran
    return Trajectory(
        id=int(row["id"]),
        query=row["query"],
        status=row["status"],
        confidence=row["confidence"],
        page_ids=json.loads(row["page_ids"]),
        path=row["path"],
        hops=int(row["hops"]),
        backtracks=int(row["backtracks"]),
        route=json.loads(row["route"]),
        reason=row["reason"] if "reason" in keys else "",
        indexed=bool(row["indexed"]),
        created_at=row["created_at"] if "created_at" in keys else "",
    )
