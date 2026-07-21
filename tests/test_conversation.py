"""The chat transcript store: create → append turns → read back → list/delete. LLM-free.

It remembers what was said (verbatim user text, the assistant's answer + provenance); it does not
manage context (that is contextualize). Turns are ordinal and stable so a follow-up rewrite and a
resumed transcript both see the conversation in order.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from libkb.api.routes import (
    PinBody,
    RenameBody,
    conversation_pin,
    conversation_rename,
    conversations_list,
)
from libkb.config import get_settings
from libkb.conversation.store import MAX_PINNED, ConversationStore


def test_create_append_and_read_back(tmp_path):
    c = ConversationStore(tmp_path / "catalog.db")
    cid = c.create(title="what is reranking?")
    assert c.exists(cid)

    c.append(cid, "user", "what is reranking?")
    c.append(
        cid,
        "assistant",
        "Reranking reorders candidates.",
        status="answered",
        reason="cascade",
        citations=[{"path": "AI ▸ RAG ▸ p.12", "page_id": "p12"}],
    )

    hist = c.history(cid)
    assert [m.role for m in hist] == ["user", "assistant"]
    assert [m.turn for m in hist] == [0, 1]  # ordinal and in order
    assert hist[1].reason == "cascade"
    assert hist[1].citations == [{"path": "AI ▸ RAG ▸ p.12", "page_id": "p12"}]
    c.close()


def test_history_limit_keeps_the_most_recent_in_order(tmp_path):
    c = ConversationStore(tmp_path / "catalog.db")
    cid = c.create()
    for i in range(6):
        c.append(cid, "user", f"m{i}")
    assert [m.text for m in c.history(cid, limit=3)] == ["m3", "m4", "m5"]
    c.close()


def test_list_transcript_and_delete(tmp_path):
    c = ConversationStore(tmp_path / "catalog.db")
    cid = c.create(title="T")
    c.append(cid, "user", "hi")

    [row] = c.list()
    assert row.id == cid and row.title == "T" and row.n_messages == 1

    out = c.transcript(cid)
    assert out is not None
    meta, msgs = out
    assert meta.id == cid and len(msgs) == 1

    assert c.delete(cid) is True
    assert c.exists(cid) is False
    assert c.transcript(cid) is None  # gone, with its messages
    c.close()


def test_unknown_conversation_is_none_not_a_crash(tmp_path):
    c = ConversationStore(tmp_path / "catalog.db")
    assert c.transcript("cv_nope") is None
    assert c.history("cv_nope") == []
    c.close()


def test_confidence_round_trips(tmp_path):
    c = ConversationStore(tmp_path / "catalog.db")
    cid = c.create()
    c.append(cid, "assistant", "ans", status="answered", confidence="high")
    assert c.history(cid)[0].confidence == "high"  # kept so a resumed answer shows its badge
    c.close()


def test_rename(tmp_path):
    c = ConversationStore(tmp_path / "catalog.db")
    cid = c.create(title="old")
    assert c.rename(cid, "  a better name  ") is True
    assert c.list()[0].title == "a better name"  # trimmed
    assert c.rename("cv_nope", "x") is False
    c.close()


def test_pin_puts_a_conversation_on_top(tmp_path):
    c = ConversationStore(tmp_path / "catalog.db")
    a = c.create(title="A")
    c.append(a, "user", "1")
    b = c.create(title="B")
    c.append(b, "user", "1")
    assert [m.id for m in c.list()][:2] == [b, a]  # newest activity first when neither is pinned

    assert c.set_pinned(a, True) == "pinned"
    top = c.list()
    assert top[0].id == a and top[0].pinned is True  # pinning floats it to the top
    c.close()


def test_pin_is_capped_at_max(tmp_path):
    c = ConversationStore(tmp_path / "catalog.db")
    ids = [c.create(title=f"c{i}") for i in range(MAX_PINNED + 1)]
    for cid in ids[:MAX_PINNED]:
        assert c.set_pinned(cid, True) == "pinned"
    assert c.set_pinned(ids[MAX_PINNED], True) == "limit"  # the 6th is refused, not applied
    assert c.set_pinned(ids[0], True) == "pinned"  # re-pinning an already-pinned one is a no-op
    assert c.set_pinned(ids[0], False) == "unpinned"  # unpinning frees a slot
    assert c.set_pinned(ids[MAX_PINNED], True) == "pinned"
    assert c.set_pinned("cv_nope", True) == "missing"
    c.close()


# ── the HTTP contract (rename / pin endpoints) ────────────────────────────────────────────────────


@pytest.fixture
def apidb(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("LIBKB_DB_PATH", str(tmp_path / "catalog.db"))
    get_settings.cache_clear()
    yield tmp_path / "catalog.db"
    get_settings.cache_clear()


def test_endpoint_rename_then_pin_shows_at_top(apidb):
    c = ConversationStore(apidb)
    cid = c.create(title="old")
    c.close()

    assert conversation_rename(cid, RenameBody(title="new name"))["title"] == "new name"
    out = conversation_pin(cid, PinBody(pinned=True))
    assert out["pinned"] is True and out["at_limit"] is False and out["max_pinned"] == MAX_PINNED

    top = conversations_list()["conversations"][0]
    assert top["id"] == cid and top["pinned"] is True and top["title"] == "new name"
    assert top["created_at"]  # the sidebar shows a specific creation time


def test_endpoint_pin_over_the_cap_reports_at_limit(apidb):
    c = ConversationStore(apidb)
    ids = [c.create(title=f"c{i}") for i in range(MAX_PINNED + 1)]
    c.close()
    for cid in ids[:MAX_PINNED]:
        conversation_pin(cid, PinBody(pinned=True))
    out = conversation_pin(ids[MAX_PINNED], PinBody(pinned=True))
    assert out["at_limit"] is True and out["pinned"] is False  # nothing else got unpinned


def test_endpoint_rename_empty_is_rejected(apidb):
    c = ConversationStore(apidb)
    cid = c.create()
    c.close()
    with pytest.raises(HTTPException):
        conversation_rename(cid, RenameBody(title="   "))
