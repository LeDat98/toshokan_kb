"""The chat transcript store: conversations and their messages.

Same SQLite file as the catalog/trajectory (D-002) — regenerable-adjacent, gitignored, and it holds
real user text, so it must never enter the tracked tree. The store is intentionally thin: it records
what was said (verbatim user text, the assistant's answer + provenance), lists/loads it back, and
supports the history sidebar's edit / delete / pin. It does NOT manage context — that is
`libkb/agent/contextualize.py`'s job — it only remembers.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

from libkb.catalog.db import connect

# At most this many conversations may be pinned to the top of the history list at once.
MAX_PINNED = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,          -- cv_<ULID>, sortable by creation time
    title       TEXT NOT NULL DEFAULT '',  -- derived from the first user message; user-editable
    pinned      INTEGER NOT NULL DEFAULT 0, -- pinned to the top of the history list
    pinned_at   TEXT NOT NULL DEFAULT '',   -- when pinned, so pins order most-recent-first
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    turn            INTEGER NOT NULL,          -- 0-based ordinal within the conversation
    role            TEXT NOT NULL,             -- user | assistant
    text            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT '',  -- assistant only: answered | not_found
    confidence      TEXT NOT NULL DEFAULT '',  -- assistant only: high | medium | low
    reason          TEXT NOT NULL DEFAULT '',  -- assistant only: which path answered
    citations       TEXT NOT NULL DEFAULT '[]',-- assistant only: [{path, page_id}]
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, turn);
"""

# Columns added after the tables first shipped. A warm db predates them, and CREATE TABLE IF NOT
# EXISTS will not add a column to an existing table — so each is ALTERed in idempotently on open.
_MIGRATIONS = (
    "ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE conversations ADD COLUMN pinned_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE messages ADD COLUMN confidence TEXT NOT NULL DEFAULT ''",
)


@dataclass
class Message:
    role: str
    text: str
    turn: int = 0
    status: str = ""
    confidence: str = ""
    reason: str = ""
    citations: list[dict] = field(default_factory=list)
    created_at: str = ""


@dataclass
class ConversationMeta:
    id: str
    title: str
    updated_at: str
    created_at: str = ""
    pinned: bool = False
    n_messages: int = 0


class ConversationStore:
    def __init__(self, db_path: Path | str) -> None:
        self._conn = connect(db_path)  # same db as the catalog; connect() is idempotent
        self._conn.executescript(SCHEMA)
        for sql in _MIGRATIONS:
            # column already present on a fresh db (SCHEMA created it) → the ALTER errors; ignore
            with contextlib.suppress(Exception):
                self._conn.execute(sql)
        self._conn.commit()

    def create(self, *, title: str = "") -> str:
        now = datetime.now(UTC).isoformat()
        cid = f"cv_{ULID()}"
        self._conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (cid, title.strip()[:120], now, now),
        )
        self._conn.commit()
        return cid

    def exists(self, cid: str) -> bool:
        row = self._conn.execute("SELECT 1 FROM conversations WHERE id = ?", (cid,)).fetchone()
        return row is not None

    def append(
        self,
        cid: str,
        role: str,
        text: str,
        *,
        status: str = "",
        confidence: str = "",
        reason: str = "",
        citations: list[dict] | None = None,
    ) -> int:
        """Append a message as the next turn and touch the conversation's updated_at."""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(turn), -1) + 1 AS next FROM messages WHERE conversation_id = ?",
            (cid,),
        ).fetchone()
        turn = int(row["next"])
        now = datetime.now(UTC).isoformat()
        cur = self._conn.execute(
            "INSERT INTO messages "
            "(conversation_id, turn, role, text, status, confidence, reason, citations, "
            "created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, turn, role, text, status, confidence, reason, json.dumps(citations or []), now),
        )
        self._conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid))
        self._conn.commit()
        return int(cur.lastrowid or 0)

    def history(self, cid: str, *, limit: int | None = None) -> list[Message]:
        """The conversation's messages, oldest → newest. `limit` keeps the most RECENT N (still in
        chronological order) — what the contextualizer needs to resolve a follow-up."""
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY turn ASC", (cid,)
        ).fetchall()
        msgs = [_msg(r) for r in rows]
        return msgs[-limit:] if limit else msgs

    def list(self, *, limit: int = 50) -> list[ConversationMeta]:
        """Conversations for the history sidebar: PINNED first (most-recently-pinned on top), then
        the rest by most-recent activity. Each carries its message count and creation time."""
        rows = self._conn.execute(
            "SELECT c.id, c.title, c.pinned, c.created_at, c.updated_at, count(m.id) AS n "
            "FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id "
            "GROUP BY c.id "
            # c.id (a ULID) is the tiebreaker: it encodes creation time, so equal timestamps still
            # order newest-first deterministically instead of by undefined row order.
            "ORDER BY c.pinned DESC, c.pinned_at DESC, c.updated_at DESC, c.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_meta(r) for r in rows]

    def transcript(self, cid: str) -> tuple[ConversationMeta, list[Message]] | None:
        row = self._conn.execute(
            "SELECT id, title, pinned, created_at, updated_at FROM conversations WHERE id = ?",
            (cid,),
        ).fetchone()
        if row is None:
            return None
        msgs = self.history(cid)
        meta = _meta(row, n=len(msgs))
        return meta, msgs

    def rename(self, cid: str, title: str) -> bool:
        cur = self._conn.execute(
            "UPDATE conversations SET title = ? WHERE id = ?", (title.strip()[:120], cid)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def set_pinned(self, cid: str, pinned: bool) -> str:
        """Pin/unpin a conversation. Returns 'pinned' | 'unpinned' | 'limit' | 'missing'. Pinning is
        capped at MAX_PINNED — a request over the cap is refused ('limit'), NOT silently applied, so
        the UI can tell the user rather than quietly dropping someone else's pin."""
        if not self.exists(cid):
            return "missing"
        if pinned:
            already = self._conn.execute(
                "SELECT pinned FROM conversations WHERE id = ?", (cid,)
            ).fetchone()
            if not int(already["pinned"]):  # only the cap matters for a NEW pin (re-pin is a no-op)
                row = self._conn.execute(
                    "SELECT count(*) AS n FROM conversations WHERE pinned = 1"
                ).fetchone()
                if int(row["n"]) >= MAX_PINNED:
                    return "limit"
            now = datetime.now(UTC).isoformat()
            self._conn.execute(
                "UPDATE conversations SET pinned = 1, pinned_at = ? WHERE id = ?", (now, cid)
            )
        else:
            self._conn.execute(
                "UPDATE conversations SET pinned = 0, pinned_at = '' WHERE id = ?", (cid,)
            )
        self._conn.commit()
        return "pinned" if pinned else "unpinned"

    def delete(self, cid: str) -> bool:
        cur = self._conn.execute("DELETE FROM conversations WHERE id = ?", (cid,))
        self._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
        self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()


def _msg(row) -> Message:
    keys = row.keys()  # `confidence` is absent on a message written before the migration ran
    return Message(
        role=row["role"],
        text=row["text"],
        turn=int(row["turn"]),
        status=row["status"],
        confidence=row["confidence"] if "confidence" in keys else "",
        reason=row["reason"],
        citations=json.loads(row["citations"]),
        created_at=row["created_at"],
    )


def _meta(row, *, n: int = 0) -> ConversationMeta:
    keys = row.keys()
    return ConversationMeta(
        id=row["id"],
        title=row["title"],
        updated_at=row["updated_at"],
        created_at=row["created_at"] if "created_at" in keys else "",
        pinned=bool(row["pinned"]) if "pinned" in keys else False,
        n_messages=int(row["n"]) if "n" in keys else n,
    )
