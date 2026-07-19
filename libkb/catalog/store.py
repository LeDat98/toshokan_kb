"""The card catalog store: add/remove question rows and brute-force cosine search.

Stored and query vectors are L2-normalized (see llm.embed), so cosine similarity is a dot
product. The full matrix is cached in memory and rebuilt lazily after any write. This is the
>~100k-question ceiling noted in D-002; past it, swap the search body for a real ANN index
behind the same `search()` signature.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import structlog

from libkb.catalog.db import connect, has_fts

log = structlog.get_logger(__name__)

_WORD = re.compile(r"[^\w]+", re.UNICODE)


def _fts_terms(query: str) -> str:
    """A user question → a safe FTS5 MATCH expression.

    Never pass raw text to MATCH: `"` starts a phrase, `*` is a prefix operator, and `AND`/`OR`/
    `NOT`/`NEAR` are keywords — a reader's sentence can easily be a syntax error, or worse, a query
    that means something other than what they typed. So: strip to words, quote each one, OR them.
    """
    words = [w for w in _WORD.split(query) if len(w) > 1]
    return " OR ".join(f'"{w}"' for w in words[:24])


@dataclass
class Hit:
    page_id: str
    book_id: str
    path: str
    text: str  # the matched question
    lang: str
    score: float


class Catalog:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._conn = connect(db_path)
        self._matrix: np.ndarray | None = None
        self._rows: list = []
        self._dirty = True
        # A single sqlite3.Connection is shared across the eval/ingest thread pool (`connect` sets
        # check_same_thread=False). sqlite3 permits that but does NOT serialise concurrent execute()
        # on one connection — two threads interleaving cursor state made `count()` see fetchone() ==
        # None (~0.5% of concurrent queries, an "impossible" NoneType on SELECT COUNT). This RLock
        # serialises every connection touch; it is reentrant because search() → _load() nest. The
        # matrix is cached in memory, so the hot search path takes the lock only on a cold or
        # after-write reload, not per query. (backlog #1 — the fix the eval pool was missing.)
        self._lock = threading.RLock()

    # -------------------------------------------------------------- write

    def embedder(self) -> str | None:
        """Which embedding model built this catalog. None on an empty one."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM catalog_meta WHERE key = 'embed_model'"
            ).fetchone()
        return row["value"] if row else None

    def _bind_embedder(self, model: str) -> None:
        """A catalog belongs to exactly ONE embedder, and this is where that is enforced.

        Two embedders are two coordinate systems. A cosine between a Gemini vector and a Qwen vector
        is not a worse number — it is not a number at all, and nothing downstream would ever notice:
        the search would return confident, ranked, meaningless results. The one failure mode we can
        neither measure nor debug is the silent one, so a mixed write raises here instead.

        Switching embedders is legitimate — it is the only way to compare two of them — but it means
        `libkb reindex --fresh`, wholesale. Never halfway.
        """
        current = self.embedder()
        if current is None:
            self._conn.execute(
                "INSERT INTO catalog_meta (key, value) VALUES ('embed_model', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (model,),
            )
        elif current != model:
            raise ValueError(
                f"this catalog was built with '{current}' and you are writing '{model}' vectors "
                f"into it. Two embedders are two vector spaces; mixing them makes every cosine "
                f"meaningless. Rebuild whole: `libkb reindex --fresh`."
            )

    def index_kind(self) -> str | None:
        """Which representation this catalog holds: `questions`, `text` or `both`. None on empty."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM catalog_meta WHERE key = 'index_kind'"
            ).fetchone()
        return row["value"] if row else None

    def _bind_index_kind(self, kind: str) -> None:
        """A catalog holds ONE representation, and this enforces it — the same reasoning as the
        embedder lock, and the same failure it prevents: SILENCE. `search()` max-pools a page's
        rows, and a question→question cosine is systematically higher than a question→text one
        (metric bug 6.6). So a catalog that quietly mixes `questions` rows (from an old reindex) and
        `text` rows (from a new partial one) would rank pages by which reindex last touched them,
        confidently and silently. A mismatched write raises: change the kind = `reindex --fresh`.
        `both` is a deliberate mix and is its own marker, distinct from either half."""
        current = self.index_kind()
        if current is None:
            self._conn.execute(
                "INSERT INTO catalog_meta (key, value) VALUES ('index_kind', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (kind,),
            )
        elif current != kind:
            raise ValueError(
                f"this catalog holds '{current}' rows and you are writing '{kind}' rows. Mixing "
                f"representations makes a page's rank depend on which reindex last touched it "
                f"(metric bug 6.6). Rebuild whole: `libkb reindex --fresh --index-kind {kind}`."
            )

    def add_page(
        self,
        *,
        page_id: str,
        book_id: str,
        path: str,
        texts: list[str],
        langs: list[str],
        embeddings: np.ndarray,
        kinds: list[str] | None = None,
        embed_model: str | None = None,
        index_kind: str | None = None,
    ) -> int:
        """`kinds` marks each row `question` (default), `term`, or `text` — see catalog/db.py.
        `index_kind` is the catalog-wide representation (see `_bind_index_kind`); pass it to lock
        the catalog to one representation, or omit it (tests, low-level writes) to skip the lock."""
        arr = np.asarray(embeddings, dtype=np.float32)
        kinds = kinds or ["question"] * len(texts)
        rows = [
            (page_id, book_id, lang, text, path, int(vec.shape[0]), vec.tobytes(), kind)
            for text, lang, vec, kind in zip(texts, langs, arr, kinds, strict=True)
        ]
        with self._lock:
            if embed_model:
                self._bind_embedder(embed_model)
            if index_kind:
                self._bind_index_kind(index_kind)
            self._conn.executemany(
                "INSERT INTO questions (page_id, book_id, lang, text, path, dim, embedding, kind) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()
            self._dirty = True
        return len(rows)

    def remove_page(self, page_id: str) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM questions WHERE page_id = ?", (page_id,))
            self._conn.commit()
            self._dirty = True
            return cur.rowcount

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM questions")
            # an empty catalog belongs to no embedder and no representation — that is what makes
            # `reindex --fresh` the sanctioned way to change either
            self._conn.execute(
                "DELETE FROM catalog_meta WHERE key IN ('embed_model', 'index_kind')"
            )
            self._conn.commit()
            self._dirty = True

    # --------------------------------------------------------------- read

    def count(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0])

    def page_ids(self) -> set[str]:
        with self._lock:
            return {r[0] for r in self._conn.execute("SELECT DISTINCT page_id FROM questions")}

    def all_questions(self) -> list[dict]:
        """Every (question → known page) row — the routing eval set (D-005)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT page_id, book_id, lang, text, path FROM questions"
            ).fetchall()
        return [dict(r) for r in rows]

    def search(
        self, query_vec: np.ndarray, *, top_k: int = 5, within: set[str] | None = None
    ) -> list[Hit]:
        """Top_k DISTINCT pages by best matching question (cosine desc).

        A page is scored by its BEST question, not its average — a page is one topic but its
        questions are alternative ways in, so max is the right pooling (§7.2).

        `within` restricts the candidates to a set of page_ids. That is what lets the shelf
        shortlist rank only the pages on the shelf the librarian is standing on, instead of ranking
        the whole library and hoping the shelf's pages float to the top.
        """
        if self._dirty or self._matrix is None:
            self._load()
        if self._matrix is None or self._matrix.shape[0] == 0:
            return []
        q = np.asarray(query_vec, dtype=np.float32).ravel()
        scores = self._matrix @ q  # both sides L2-normalized ⇒ cosine
        best: dict[str, Hit] = {}
        for row, score in zip(self._rows, scores, strict=True):
            pid = row["page_id"]
            if within is not None and pid not in within:
                continue
            s = float(score)
            current = best.get(pid)
            if current is None or s > current.score:
                best[pid] = Hit(
                    page_id=pid,
                    book_id=row["book_id"],
                    path=row["path"],
                    text=row["text"],
                    lang=row["lang"],
                    score=s,
                )
        return sorted(best.values(), key=lambda h: h.score, reverse=True)[:top_k]

    def search_lexical(
        self, query: str, *, top_k: int = 5, within: set[str] | None = None
    ) -> list[Hit]:
        """BM25 over the question text (FTS5). Catches what embeddings structurally miss: rare terms
        and named entities — HNSW, GMROI, a SKU code, a Japanese retail term.

        Returns [] when SQLite has no FTS5 build, or when the query has no usable terms. `score` is
        a rank-friendly transform of BM25 (higher = better) and is NOT comparable to a cosine — the
        two rankings are fused by RANK, never by score (catalog/search.py).
        """
        terms = _fts_terms(query)
        with self._lock:
            if not terms or not has_fts(self._conn):
                return []
            try:
                rows = self._conn.execute(
                    "SELECT q.page_id, q.book_id, q.path, q.text, q.lang, "
                    "bm25(questions_fts) AS score "
                    "FROM questions_fts JOIN questions q ON q.id = questions_fts.rowid "
                    "WHERE questions_fts MATCH ? ORDER BY score LIMIT ?",
                    (terms, top_k * 8),  # over-fetch: many rows collapse onto the same page
                ).fetchall()
            except sqlite3.OperationalError:  # a malformed MATCH expression must not break a walk
                return []

        best: dict[str, Hit] = {}
        for row in rows:
            pid = row["page_id"]
            if within is not None and pid not in within:
                continue
            score = -float(row["score"])  # bm25() returns lower-is-better
            current = best.get(pid)
            if current is None or score > current.score:
                best[pid] = Hit(
                    page_id=pid,
                    book_id=row["book_id"],
                    path=row["path"],
                    text=row["text"],
                    lang=row["lang"],
                    score=score,
                )
        return sorted(best.values(), key=lambda h: h.score, reverse=True)[:top_k]

    def lexical_row_scores(self, query: str, *, limit: int = 500) -> dict[int, float]:
        """Raw BM25 scores keyed by row id (higher = better). Row-level, not page-level, because the
        held-out probes must be able to MASK the query's own rows — a lexical ranker that is allowed
        to match the row it was generated from scores 100% and measures nothing."""
        terms = _fts_terms(query)
        with self._lock:
            if not terms or not has_fts(self._conn):
                return {}
            try:
                rows = self._conn.execute(
                    "SELECT rowid, bm25(questions_fts) AS score FROM questions_fts "
                    "WHERE questions_fts MATCH ? ORDER BY score LIMIT ?",
                    (terms, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                return {}
        return {int(r["rowid"]): -float(r["score"]) for r in rows}

    def vectors(self) -> tuple[np.ndarray, list]:
        """The full (N, dim) matrix + its rows, in insertion order. Used by the free
        held-out probe (evals/catalog_probe.py) to calibrate the shortcut gate."""
        if self._dirty or self._matrix is None:
            self._load()
        return self._matrix, self._rows  # type: ignore[return-value]

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------ internal

    def _load(self) -> None:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, page_id, book_id, lang, text, path, dim, embedding, kind "
                "FROM questions ORDER BY id"
            ).fetchall()
        self._rows = rows
        if not rows:
            self._matrix = np.empty((0, 0), dtype=np.float32)
        else:
            self._matrix = np.vstack(
                [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]
            )
        self._dirty = False
