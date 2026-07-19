"""SQLite connection + schema for the card catalog.

One row per (page, question). Embeddings are stored as raw float32 bytes (L2-normalized at
write time) plus their dimension, so search is a plain dot product. WAL mode + a permissive
same-thread setting let the API's worker threads read while ingest writes.

`questions_fts` is an FTS5 mirror of `text`, kept in sync by triggers. It was built for the reason
§7.3 gives — dense retrieval has a structural blind spot for **rare terms and named entities**
("HNSW", "GMROI", a SKU code, a Japanese retail term), which BM25 matches exactly.

**But fusing it into retrieval was MEASURED and REFUTED (D-032).** On both query distributions we
have, adding BM25 makes recall worse at every fusion weight, monotonically: generated questions
LOI page R@10 90.7% → 78.6%, and held-out colloquial paraphrases R@1 83.3% → 43.3%. A reader's
paraphrase reuses almost none of the library's exact words, so lexical matching latches onto common
ones and drags noise to the top.

The index is kept, and `hybrid_shortlist` can switch the fusion on, because the rare-term mechanism
is real (see tests/test_hybrid.py) — it just is not what this corpus's queries are made of. Revisit
when the trajectory log (§8.4) shows real queries where those terms actually appear.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id    TEXT NOT NULL,
    book_id    TEXT NOT NULL,
    lang       TEXT NOT NULL,
    text       TEXT NOT NULL,
    path       TEXT NOT NULL,
    dim        INTEGER NOT NULL,
    embedding  BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_questions_page ON questions(page_id);
CREATE TABLE IF NOT EXISTS catalog_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

# `kind` separates the two things a catalog row can be (§8.2):
#   question — "how is GMROI calculated?"   (an entry point phrased as a reader would)
#   term     — "GMROI · gross margin return on investment · lợi nhuận gộp trên vốn tồn"
#             (an entry VOCABULARY: synonyms, abbreviations, named entities —
#              USE / UF / RT in thesaurus terms, ISO 25964)
# Kept separable on purpose: whether terms help retrieval or add noise is an open question, and a
# column we can filter on is the difference between measuring that and guessing at it.
MIGRATIONS = [
    "ALTER TABLE questions ADD COLUMN kind TEXT NOT NULL DEFAULT 'question'",
]

FTS_BUILD = "2"  # bump to force a one-off reindex (tokenizer change, new indexed column, …)

# Separate script: an FTS5 build is not guaranteed to be present, and a catalog without a lexical
# index must still work (dense-only) rather than refuse to open.
FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS questions_fts USING fts5(
    text,
    content='questions',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS questions_ai AFTER INSERT ON questions BEGIN
    INSERT INTO questions_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS questions_ad AFTER DELETE ON questions BEGIN
    INSERT INTO questions_fts(questions_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS questions_au AFTER UPDATE ON questions BEGIN
    INSERT INTO questions_fts(questions_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO questions_fts(rowid, text) VALUES (new.id, new.text);
END;
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    # Under a concurrent ingest/eval pool (backlog #1) more than one thread may write at once. WAL
    # allows one writer + many readers; a SECOND writer would otherwise get SQLITE_BUSY at once.
    # busy_timeout makes it WAIT (here, up to 30s) for the lock instead — the difference between a
    # thread that queues and a thread that crashes the run.
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    _migrate(conn)
    if has_fts(conn):
        conn.executescript(FTS_SCHEMA)
        _backfill_fts(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive column migrations. Idempotent: a duplicate-column error means it is already done."""
    for statement in MIGRATIONS:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise
    conn.commit()


def has_fts(conn: sqlite3.Connection) -> bool:
    """Is this SQLite built with FTS5? Without it the catalog stays dense-only, which is a
    degradation (rare terms get worse) but never a failure."""
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS _fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


def _backfill_fts(conn: sqlite3.Connection) -> None:
    """Index the rows written before FTS existed (i.e. every catalog built so far).

    Detecting "is the index empty?" is a trap here, and both obvious answers are wrong:
      - `count(*) FROM questions_fts` is delegated to the content table (this is an
        **external-content** table), so it reports every row as indexed even when the index holds
        nothing — the guard passes, the rebuild never runs, and every MATCH silently returns [];
      - `count(*) FROM questions_fts_data` counts opaque internal segments, not documents. An empty
        index does not reliably have exactly one row.

    So we do not infer. We record what we did, in `catalog_meta`, and bump FTS_BUILD when the index
    definition changes.
    """
    row = conn.execute("SELECT value FROM catalog_meta WHERE key = 'fts_build'").fetchone()
    if row and row["value"] == FTS_BUILD:
        return
    conn.execute("INSERT INTO questions_fts(questions_fts) VALUES ('rebuild')")
    conn.execute(
        "INSERT INTO catalog_meta (key, value) VALUES ('fts_build', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (FTS_BUILD,),
    )
    conn.commit()
