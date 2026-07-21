"""The semantic answer cache store: question embedding -> cached answer, with cosine lookup.

Same SQLite file as the catalog (D-002) — regenerable-adjacent, gitignored (it holds real user
questions + answers). Vectors are L2-normalized on write so cosine is a dot product; the matrix is
rebuilt lazily after any write, brute-force over the (small) set of cached questions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from libkb.catalog.db import connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS answer_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query           TEXT NOT NULL,
    dim             INTEGER NOT NULL,
    embedding       BLOB NOT NULL,
    answer          TEXT NOT NULL,
    citations       TEXT NOT NULL DEFAULT '[]',   -- [{path, page_id}]
    confidence      TEXT NOT NULL DEFAULT '',
    source_page_ids TEXT NOT NULL DEFAULT '[]',   -- pages the answer was built from (invalidation)
    curated         INTEGER NOT NULL DEFAULT 0,   -- a human edited/approved this answer (sticky)
    enabled         INTEGER NOT NULL DEFAULT 1,
    hits            INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    last_hit_at     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS cache_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


@dataclass
class CacheEntry:
    id: int
    query: str
    answer: str
    citations: list[dict] = field(default_factory=list)
    confidence: str = ""
    source_page_ids: list[str] = field(default_factory=list)
    curated: bool = False
    enabled: bool = True
    hits: int = 0
    created_at: str = ""
    last_hit_at: str = ""


@dataclass
class CacheHit:
    entry: CacheEntry
    score: float


def _norm(vec) -> np.ndarray:
    v = np.asarray(vec, dtype=np.float32).ravel()
    n = float(np.linalg.norm(v))
    return v / n if n else v


class AnswerCache:
    def __init__(self, db_path: Path | str) -> None:
        self._conn = connect(db_path)  # same db as the catalog; connect() is idempotent
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._matrix: np.ndarray | None = None
        self._rows: list = []
        self._dirty = True

    # ── global on/off (persisted, so the UI toggle survives a restart) ────────────────────────────

    def is_enabled(self) -> bool:
        row = self._conn.execute("SELECT value FROM cache_state WHERE key = 'enabled'").fetchone()
        return row is None or row["value"] == "1"  # default ON when unset

    def set_enabled(self, enabled: bool) -> None:
        self._conn.execute(
            "INSERT INTO cache_state (key, value) VALUES ('enabled', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("1" if enabled else "0",),
        )
        self._conn.commit()

    # ── write ─────────────────────────────────────────────────────────────────────────────────────

    def put(
        self,
        query: str,
        vec,
        answer: str,
        citations: list[dict],
        confidence: str,
        source_page_ids: list[str],
    ) -> int:
        v = _norm(vec)
        now = datetime.now(UTC).isoformat()
        cur = self._conn.execute(
            "INSERT INTO answer_cache "
            "(query, dim, embedding, answer, citations, confidence, source_page_ids, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                query,
                int(v.shape[0]),
                v.tobytes(),
                answer,
                json.dumps(citations, ensure_ascii=False),
                confidence,
                json.dumps(source_page_ids),
                now,
                now,
            ),
        )
        self._conn.commit()
        self._dirty = True
        return int(cur.lastrowid or 0)

    def record_hit(self, entry_id: int) -> None:
        self._conn.execute(
            "UPDATE answer_cache SET hits = hits + 1, last_hit_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), entry_id),
        )
        self._conn.commit()

    def update_answer(self, entry_id: int, answer: str) -> bool:
        """Edit an answer — this marks it CURATED (human-owned), which makes it sticky."""
        cur = self._conn.execute(
            "UPDATE answer_cache SET answer = ?, curated = 1, updated_at = ? WHERE id = ?",
            (answer, datetime.now(UTC).isoformat(), entry_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def set_entry_enabled(self, entry_id: int, enabled: bool) -> bool:
        cur = self._conn.execute(
            "UPDATE answer_cache SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, datetime.now(UTC).isoformat(), entry_id),
        )
        self._conn.commit()
        self._dirty = True
        return cur.rowcount > 0

    def delete(self, entry_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM answer_cache WHERE id = ?", (entry_id,))
        self._conn.commit()
        self._dirty = True
        return cur.rowcount > 0

    def invalidate_pages(self, page_ids: set[str]) -> int:
        """Drop NON-curated entries whose evidence includes any of `page_ids` — their source
        changed, so the cached answer may be stale. Curated (human-owned) entries are KEPT (only a
        human unmakes a human's answer). Returns how many were dropped."""
        dropped = 0
        rows = self._conn.execute(
            "SELECT id, source_page_ids FROM answer_cache WHERE curated = 0"
        ).fetchall()
        for row in rows:
            if page_ids & set(json.loads(row["source_page_ids"])):
                self._conn.execute("DELETE FROM answer_cache WHERE id = ?", (row["id"],))
                dropped += 1
        if dropped:
            self._conn.commit()
            self._dirty = True
        return dropped

    # ── read / search ─────────────────────────────────────────────────────────────────────────────

    def search(self, query_vec, *, threshold: float, margin: float = 0.0) -> CacheHit | None:
        """The best ENABLED cached question by cosine, IF it clears the threshold (and, when set, a
        margin over the runner-up). A miss returns None — the caller then answers normally.

        High precision is the whole point: a wrong hit serves a DIFFERENT question's answer, so the
        threshold is deliberately conservative and this returns nothing rather than a weak match."""
        if self._dirty or self._matrix is None:
            self._load()
        if self._matrix is None or self._matrix.shape[0] == 0:
            return None
        q = _norm(query_vec)
        if q.shape[0] != self._matrix.shape[1]:
            return None  # dimension mismatch (embedder changed) — fail to a miss, never crash
        scores = self._matrix @ q
        # only ENABLED rows are eligible
        eligible = [
            (float(s), row) for s, row in zip(scores, self._rows, strict=True) if row["enabled"]
        ]
        if not eligible:
            return None
        eligible.sort(key=lambda t: t[0], reverse=True)
        best_score, best_row = eligible[0]
        if best_score < threshold:
            return None
        if margin > 0.0 and len(eligible) > 1 and best_score - eligible[1][0] < margin:
            return None  # too close to a second cached question to be sure which one they mean
        return CacheHit(entry=_entry(best_row), score=best_score)

    def list(self, *, limit: int = 100) -> list[CacheEntry]:
        """Cached answers for the management UI — most-hit first, then newest."""
        rows = self._conn.execute(
            "SELECT * FROM answer_cache ORDER BY hits DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_entry(r) for r in rows]

    def get(self, entry_id: int) -> CacheEntry | None:
        row = self._conn.execute("SELECT * FROM answer_cache WHERE id = ?", (entry_id,)).fetchone()
        return _entry(row) if row else None

    def count(self) -> int:
        return int(self._conn.execute("SELECT count(*) FROM answer_cache").fetchone()[0])

    def close(self) -> None:
        self._conn.close()

    def _load(self) -> None:
        rows = self._conn.execute("SELECT * FROM answer_cache ORDER BY id").fetchall()
        self._rows = rows
        if not rows:
            self._matrix = np.empty((0, 0), dtype=np.float32)
        else:
            self._matrix = np.vstack(
                [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]
            )
        self._dirty = False


def _entry(row) -> CacheEntry:
    return CacheEntry(
        id=int(row["id"]),
        query=row["query"],
        answer=row["answer"],
        citations=json.loads(row["citations"]),
        confidence=row["confidence"],
        source_page_ids=json.loads(row["source_page_ids"]),
        curated=bool(row["curated"]),
        enabled=bool(row["enabled"]),
        hits=int(row["hits"]),
        created_at=row["created_at"],
        last_hit_at=row["last_hit_at"],
    )
