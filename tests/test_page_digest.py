"""The librarian puts the book back on the shelf (docs/ROUTING_REDESIGN.md §6).

Every LLM turn resends the whole conversation, so a page read on turn 3 of an 8-turn walk is
re-billed 5 more times — even after the librarian read it, rejected it, and walked on.

**The feature is OFF by default (D-033), and these tests turn it on.** It works exactly as designed:
the conversation stops growing and plateaus. It still LOST the eval — 17% MORE tokens per query at
identical answer_acc — because the librarian, robbed of the full text, compensates by reading more
pages and taking more turns. The saving is eaten by the behaviour it induces. Kept, tested, and
switchable, because the last test here (free re-reads) attacks that exact mechanism and may yet make
it pay; but it does not get shipped on hope.

The safety argument the design rests on, pinned below: `compose_answer` rebuilds its evidence from
the `PageContent` objects in `NavState.pages`, which never enter the navigator's conversation — so
compressing that conversation **cannot cost the answer anything**. All LLM-free.
"""

import pytest

from libkb import seed
from libkb.agent.navigator import navigate
from libkb.config import get_settings
from libkb.library.store import LibraryStore
from libkb.llm.client import LLMResult, ToolCall

# a phrase from the END of the "What is RAG" page: present in the full text, absent
# from a digest built out of its one_line + first two sentences
LATE_IN_BODY = "failure modes are retrieval misses"


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("LIBKB_PAGE_DIGEST_AFTER_TURNS", "1")  # OFF in production (D-033)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store(tmp_path):
    s = LibraryStore(tmp_path / "library")
    s.init_library()
    seed.apply(s)
    return s


class RecordingLLM:
    """Scripted walk that keeps the exact `turns` it was handed on every call."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0
        self.seen: list[list] = []

    def load_prompt(self, name, **kw):
        return f"[{name}]"

    def generate(self, contents, **kwargs):
        self.seen.append([_flatten(t) for t in contents])
        if self.calls < len(self._script):
            name, args = self._script[self.calls]
            self.calls += 1
            return LLMResult(text=None, tool_calls=[ToolCall(name=name, args=args)])
        self.calls += 1
        return LLMResult(text="", tool_calls=[ToolCall(name="not_found", args={"reason": "end"})])


def _flatten(turn) -> str:
    if turn.tool_responses:
        return "\n".join(str(r.response.get("result", "")) for r in turn.tool_responses)
    return turn.text or ""


def _walk_reading_two_pages():
    # turn 4 reads page 1, turn 5 reads page 2, turn 6 is one more step — so the LAST prompt the
    # model is actually handed (before turn 7) is the first one in which page 1 has gone stale.
    # Without that extra turn the shelving happens after the final generate and is unobservable.
    return [
        ("browse", {"target": "AI"}),
        ("browse", {"target": "RAG"}),
        ("open_shelf", {}),
        ("read_page", {"title": "What is RAG"}),  # page 1 — will go stale
        ("read_page", {"title": "Reranking & Cross-encoders"}),  # page 2 — the recent one
        ("go_back", {"reason": "seen enough"}),
        ("found", {"note": "here"}),
    ]


def _last_prompt(llm) -> str:
    """The final prompt the model was actually handed — i.e. what we were actually billed for."""
    return "\n".join(llm.seen[-1])


def test_an_old_page_is_shelved_but_the_recent_one_is_kept_in_full(store):
    llm = RecordingLLM(_walk_reading_two_pages())
    result = navigate("what is reranking?", store=store, llm=llm)
    assert result.status == "FOUND"

    final = _last_prompt(llm)
    # page 1 was read, then walked past — it is now a gist
    assert "(read — the full text is retained as evidence; this is the gist)" in final
    assert LATE_IN_BODY not in final  # the rest of its body is gone from context
    # page 2 is the most recent read — the librarian may still need to compare it head to head
    assert "cross-encoder" in final.lower()


def test_the_answer_still_gets_both_pages_in_full(store):
    """The property the whole design rests on: the evidence lives OUTSIDE the conversation."""
    llm = RecordingLLM(_walk_reading_two_pages())
    result = navigate("what is reranking?", store=store, llm=llm)

    assert len(result.pages) == 2
    bodies = " ".join(p.markdown for p in result.pages)
    # both full texts survive intact for compose_answer, even though one was shelved mid-walk
    assert "Retrieval-Augmented Generation" in bodies
    assert "cross-encoder" in bodies.lower()


def test_digest_keeps_enough_to_judge_have_i_got_enough(store):
    """A bare path would not let the navigator decide whether to call found(). A gist does."""
    llm = RecordingLLM(_walk_reading_two_pages())
    navigate("what is reranking?", store=store, llm=llm)

    final = _last_prompt(llm)
    digest = next(b for b in final.split("[PAGE") if "this is the gist" in b)
    assert "What is RAG" in digest  # the path, so it can still be cited/revisited
    assert len(digest) > 80  # …and a gist of the content, not just a stub
    assert len(digest) < 700  # …but nothing like the full page


def test_shelving_can_be_switched_off_for_an_ab(store, monkeypatch):
    monkeypatch.setenv("LIBKB_PAGE_DIGEST_AFTER_TURNS", "-1")
    get_settings.cache_clear()
    llm = RecordingLLM(_walk_reading_two_pages())
    navigate("what is reranking?", store=store, llm=llm)

    final = _last_prompt(llm)
    assert "this is the gist" not in final
    assert LATE_IN_BODY in final  # page 1 still there, in full


def test_digesting_immediately_still_leaves_the_page_readable_on_its_own_turn(store, monkeypatch):
    """keep_full=0 shelves a page as soon as its turn is over — but the model still SAW it in full
    on the turn it read it, which is when it decides whether the page was any use."""
    monkeypatch.setenv("LIBKB_PAGE_DIGEST_AFTER_TURNS", "0")
    get_settings.cache_clear()
    llm = RecordingLLM(_walk_reading_two_pages())
    result = navigate("what is reranking?", store=store, llm=llm)

    # the turn right after page 1 was read: it was still full then
    after_page_1 = "\n".join(llm.seen[4])
    assert LATE_IN_BODY in after_page_1
    # by the end, both pages are gists
    assert _last_prompt(llm).count("this is the gist") == 2
    assert len(result.pages) == 2  # …and the answer still gets both


def test_a_page_the_librarian_rejects_stops_costing_tokens(store):
    """The case the whole section is about: read a page, decide it is useless, walk on. It must not
    keep being re-billed on every remaining turn."""
    llm = RecordingLLM(
        [
            ("browse", {"target": "AI"}),
            ("browse", {"target": "RAG"}),
            ("open_shelf", {}),
            ("read_page", {"title": "What is RAG"}),  # a dead end
            ("go_back", {"reason": "not it"}),
            ("browse", {"target": "LLM"}),
            ("open_shelf", {}),
            ("read_page", {"title": "Attention & KV cache"}),
            ("found", {"note": "here"}),
        ]
    )
    navigate("how does the kv cache work?", store=store, llm=llm)

    first_after_read = "\n".join(llm.seen[4])
    final = _last_prompt(llm)
    assert LATE_IN_BODY in first_after_read  # billed once, in full
    assert LATE_IN_BODY not in final  # and never at full length again


def test_rereading_a_page_is_free_and_does_not_duplicate_the_evidence(store):
    """The digest takes a page's full text out of the conversation. So the librarian must be able to
    get it back — otherwise the digest is a trap, and he compensates by reading MORE pages, which is
    exactly what the first eval cases showed him doing (he hit the page budget).

    But a re-read must not burn a page-budget slot for evidence he already holds, and must not hand
    `compose_answer` the same page twice as though it were two independent sources.
    """
    llm = RecordingLLM(
        [
            ("browse", {"target": "AI"}),
            ("browse", {"target": "RAG"}),
            ("open_shelf", {}),
            ("read_page", {"title": "What is RAG"}),
            ("read_page", {"title": "Reranking & Cross-encoders"}),
            ("read_page", {"title": "What is RAG"}),  # ← wants the shelved page back
            ("found", {"note": "here"}),
        ]
    )
    result = navigate("what is reranking?", store=store, llm=llm)

    assert len(result.pages) == 2  # not 3 — the same page is not two sources
    assert len({p.page_id for p in result.pages}) == 2
    # and he really got the full text back, not a "budget reached" refusal
    handed_back = "\n".join(llm.seen[6])
    assert "you have read this page; here it is again in full" in handed_back
    assert LATE_IN_BODY in handed_back
