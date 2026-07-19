"""Retrieval as a cascade, not a walk (docs/RETRIEVAL_REDESIGN.md). All LLM-free.

The diagnosis these tests encode: **we were using the LLM as the sieve; it should be the oracle.**
The embedder is a bad oracle (top-1 39.3% on an unanticipated intent) and a good sieve (top-3
contains the answer 96.7% of the time — exactly what the 13-call walk achieves). So: sieve for free,
then spend the LLM once, on a handful.

The property that makes it cheap is not compression. It is **where the text sits**: a page in the
navigator's conversation is re-billed on every later turn; a page in the answerer's call is billed
once. So the librarian triages on SECTION HEADERS (59 tokens) and never sees a page body until the
basket is opened.
"""

import numpy as np
import pytest

from libkb import seed
from libkb.agent.cascade import answer_by_cascade
from libkb.catalog.store import Catalog
from libkb.config import get_settings
from libkb.library.sections import (
    pick_sections,
    query_snippet,
    section_index,
    split_sections,
)
from libkb.library.store import LibraryStore

PAGE = """# Inventory Turnover

Intro line about the metric.

## Definition
Turnover is COGS divided by average inventory.

## Formula
COGS / ((opening + closing) / 2).

## Worked example
A store with 2M COGS and 500k average inventory turns 4x.
"""


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("LIBKB_RETRIEVAL_MODE", "cascade")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store(tmp_path):
    s = LibraryStore(tmp_path / "library")
    s.init_library()
    seed.apply(s)
    return s


# ------------------------------------------------------------------ sections


def test_a_page_splits_at_its_own_headings():
    # the H1 is not a boundary (it appears once); the repeated level is H2. But the text ABOVE the
    # first H2 is still a section — often the one holding the definition — so it is nameable, under
    # the page's own H1.
    assert section_index(PAGE) == ["Inventory Turnover", "Definition", "Formula", "Worked example"]
    assert "Intro line" in split_sections(PAGE)[0].body


def test_a_section_is_an_order_of_magnitude_cheaper_than_a_page():
    """MEASURED on the live library: page 1,571 tok · section headers 59 · two sections 516."""
    whole = len(PAGE) // 4
    formula = pick_sections(PAGE, ["Formula"])
    assert "COGS / ((opening" in formula
    assert "Worked example" not in formula  # only what was asked for
    assert len(formula) // 4 < whole / 2


def test_asking_for_nothing_recognisable_hands_over_the_page_not_silence():
    """Evidence the answerer never receives is evidence that cannot be cited (P6). A near-miss must
    degrade to 'give him something', never to 'give him nothing'."""
    assert "Formula" in pick_sections(PAGE, ["Section That Does Not Exist"])
    assert "Formula" in pick_sections(PAGE, [])


def test_a_misparsed_giant_page_cannot_eat_the_answer_budget():
    """A real one is in the library: a mis-parsed PDF landed a 12,842-token 'page'."""
    giant = "# Doc\n\n" + "\n\n".join(f"## S{i}\n" + ("filler " * 400) for i in range(20))
    assert len(giant) // 4 > 10_000
    capped = pick_sections(giant, [], max_tokens=1000)
    assert len(capped) // 4 <= 1400  # the first section may overshoot; nothing after it is taken


def test_headings_inside_code_fences_are_not_sections():
    md = "# T\n\n## Real\n\n```\n# not a heading\n## nor this\n```\n\n## Also real\n"
    assert section_index(md) == [
        "T",
        "Real",
        "Also real",
    ]  # the fenced ones are code, not structure


# --------------------------------------------- the query-relevant snippet (D-050)


def test_snippet_surfaces_the_passage_that_answers_the_query():
    """A TEXT index throws away the sieve's reason for ranking a page; this recovers it, model-free.
    The snippet is the sentence carrying the most DISTINCT query content-words — here the definition
    (shares 'turnover' + 'COGS'), never the contentless intro line."""
    snip = query_snippet(PAGE, "what is the turnover COGS definition?")
    assert "COGS divided by average inventory" in snip
    assert "Intro line" not in snip


def test_snippet_is_blank_when_nothing_overlaps_rather_than_misleading():
    """An honest blank beats a confident first sentence: the spine label already carries the gist,
    and a snippet that shares no content word with the query would only mislead triage."""
    assert query_snippet(PAGE, "quarterly marketing budget in euros") == ""


def test_snippet_ignores_stopword_only_overlap():
    """Overlap on 'the'/'is'/'of' is not aboutness — a span must share a CONTENT word to score."""
    assert query_snippet("The report is on the table.", "what is the of and to") == ""


def test_snippet_is_capped_and_stripped_of_markdown_noise():
    long = "# Heading\n\n- " + "widget " * 100 + "sprocket."
    snip = query_snippet(long, "widget sprocket", max_chars=40)
    assert len(snip) <= 40
    assert not snip.startswith(("#", "-"))  # leading list/heading markers removed


# ------------------------------------------------------------------ the cascade


def _unit(*v):
    a = np.asarray([v], dtype=np.float32)
    return a / np.linalg.norm(a)


class FakeLLM:
    """Embeds the query onto the target page's axis; triages to a scripted basket."""

    def __init__(self, placements, target, basket, answers=None):
        self._p = placements
        self._target = target
        self._basket = basket
        self._answers = list(answers or [])
        self.json_calls = 0
        self.triage_prompt = ""

    def embed(self, texts, *, task="RETRIEVAL_DOCUMENT", model=None):
        return _unit(*self._p[self._target])

    def load_prompt(self, name, **kw):
        self.last_prompt = name
        if name == "triage":
            self.triage_prompt = kw.get("candidates", "")
        return f"[{name}] " + " ".join(f"{k}={v}" for k, v in kw.items())

    def generate_json(self, contents, *, schema, model=None, **kw):
        self.json_calls += 1
        if "[triage]" in str(contents):
            return {"basket": self._basket.pop(0) if self._basket else []}
        return (
            self._answers.pop(0)
            if self._answers
            else {"answer": "Because X.", "confidence": "high", "sufficient": True}
        )


def _library(store, tmp_path, bodies):
    """Give real seed pages our own bodies + vectors, one axis each.

    Pages are taken across the whole RAG shelf, not one book: the cascade fetches `cascade_k`
    candidates per round, so a 3-page book cannot exercise the second round at all.
    """
    shelf = store.resolve_path("ai/rag")
    ids = [
        p.id
        for book in store.children(shelf)
        if book.kind == "book"
        for p in store.children(book.id)
        if p.kind == "page"
    ][: len(bodies)]
    assert len(ids) == len(bodies), f"the seed shelf has only {len(ids)} pages"

    cat = Catalog(tmp_path / "catalog.db")
    placements = {}
    for i, (page_id, body) in enumerate(zip(ids, bodies, strict=True)):
        path = store.path_str(page_id)
        vec = [0.0] * len(bodies)
        vec[i] = 1.0
        placements[path] = tuple(vec)
        entry = store._entry(page_id)  # noqa: SLF001 — a test fixture writing a page body
        entry.path.write_text(
            f"---\nid: {page_id}\ntitle: {store.get(page_id).title}\n---\n\n{body}",
            encoding="utf-8",
        )
        cat.add_page(
            page_id=page_id,
            book_id=entry.parent_id,
            path=path,
            texts=[f"q for {path}"],
            langs=["en"],
            embeddings=_unit(*placements[path]),
        )
    return cat, placements, [store.path_str(i) for i in ids]


def test_the_librarian_triages_on_headers_and_never_sees_a_page_body(store, tmp_path):
    """The whole economic argument. If a body reaches the triage prompt, the design is void."""
    cat, placements, paths = _library(store, tmp_path, [PAGE, PAGE, PAGE])
    target = paths[0]
    llm = FakeLLM(
        placements, target, basket=[[{"page": target, "sections": ["Formula"], "why": "has it"}]]
    )

    result = answer_by_cascade("how is turnover calculated?", store=store, catalog=cat, llm=llm)
    cat.close()

    assert "Sections:" in llm.triage_prompt
    assert "Formula" in llm.triage_prompt  # the header, yes
    assert "COGS / ((opening" not in llm.triage_prompt  # the BODY, never
    assert result.answer.status == "answered"
    assert llm.json_calls == 2  # triage + answer. Two calls, not thirteen.


def test_only_the_requested_sections_reach_the_answerer(store, tmp_path):
    cat, placements, paths = _library(store, tmp_path, [PAGE, PAGE, PAGE])
    target = paths[0]
    llm = FakeLLM(placements, target, basket=[[{"page": target, "sections": ["Formula"]}]])

    result = answer_by_cascade("formula?", store=store, catalog=cat, llm=llm)
    cat.close()

    [evidence] = result.nav.pages
    assert "COGS / ((opening" in evidence.markdown  # the section asked for
    assert "A store with 2M COGS" not in evidence.markdown  # the one that was not
    assert result.nav.pages[0].page_id  # …and it is still a real, citable page


def test_an_empty_basket_widens_instead_of_giving_up(store, tmp_path, monkeypatch):
    """The 'rollback' the walk needed go_back() for. Here it is free: the next candidates were
    already ranked in the free proposal step, so widening costs nothing but one more triage."""
    # a small triage batch so the 6-page library spans two rounds (production triages the whole
    # window in one call; the multi-round widen path still exists and is what this test exercises)
    monkeypatch.setenv("LIBKB_CASCADE_K", "5")
    get_settings.cache_clear()
    cat, placements, paths = _library(store, tmp_path, [PAGE] * 6)
    llm = FakeLLM(
        placements,
        target=paths[0],
        # round 1: nothing here answers it. round 2 sees the candidates round 1 did not.
        basket=[[], [{"page": paths[5], "sections": ["Formula"]}]],
    )
    result = answer_by_cascade("formula?", store=store, catalog=cat, llm=llm)
    cat.close()

    assert result.answer.status == "answered"
    assert result.rounds == 2
    assert [b.path for b in result.basket] == [paths[5]]


def test_a_null_basket_is_treated_as_empty_not_a_crash(store, tmp_path, monkeypatch):
    """A schema can REQUIRE `basket` and still receive `{"basket": null}` — Qwen returns exactly
    this to mean "nothing relevant", and `.get("basket", [])` then yields None, not the default.
    Slicing it threw `'NoneType' object is not subscriptable` on ~2% of fetch=50 cases. A null
    basket is an empty round: widen, do not crash."""
    monkeypatch.setenv("LIBKB_CASCADE_K", "5")  # small batch → two rounds over the 6-page library
    get_settings.cache_clear()
    cat, placements, paths = _library(store, tmp_path, [PAGE] * 6)
    llm = FakeLLM(
        placements,
        target=paths[0],
        basket=[
            None,
            [{"page": paths[5], "sections": ["Formula"]}],
        ],  # round 1 null → round 2 finds it
    )
    result = answer_by_cascade("formula?", store=store, catalog=cat, llm=llm)
    cat.close()
    assert result.answer.status == "answered"
    assert [b.path for b in result.basket] == [paths[5]]


def test_wrong_section_of_the_right_page_reopens_it_instead_of_abandoning_it(store, tmp_path):
    """The bug that cost this architecture its first eval (D-035).

    The librarian names sections from a list of TITLES, and a title easily hides the paragraph that
    answers. When the answerer then says "insufficient", the old code went looking for *other pages*
    — throwing away the right one because it had been opened at the wrong chapter. In all four cases
    the cascade lost, the sieve had ranked the target page **#1**.

    So: before widening, re-open what we already hold, in full. One call, no search.
    """
    cat, placements, paths = _library(store, tmp_path, [PAGE] * 6)
    llm = FakeLLM(
        placements,
        target=paths[0],
        basket=[[{"page": paths[0], "sections": ["Definition"]}]],  # the wrong section
        answers=[
            {"answer": "not enough", "confidence": "low", "sufficient": False},
            {"answer": "Now I can answer.", "confidence": "high", "sufficient": True},
        ],
    )
    result = answer_by_cascade("formula?", store=store, catalog=cat, llm=llm)
    cat.close()

    assert result.answer.status == "answered"
    assert any("re-opening" in e.title for e in result.nav.events)
    assert result.rounds == 1  # it never needed to widen — the page was right all along
    [evidence] = result.nav.pages
    assert "COGS / ((opening" in evidence.markdown  # the section it FIRST missed is now present


def test_a_page_that_still_cannot_answer_in_full_does_widen(store, tmp_path, monkeypatch):
    """…but re-opening is not an excuse to cling. If the whole page still does not answer, go and
    look at candidates we have not seen. They cost nothing: they were ranked in the free step."""
    monkeypatch.setenv("LIBKB_CASCADE_K", "5")  # small batch → two rounds over the 6-page library
    get_settings.cache_clear()
    cat, placements, paths = _library(store, tmp_path, [PAGE] * 6)
    llm = FakeLLM(
        placements,
        target=paths[0],
        basket=[
            [{"page": paths[0], "sections": ["Definition"]}],
            [{"page": paths[5], "sections": ["Formula"]}],
        ],
        answers=[
            {"answer": "no", "confidence": "low", "sufficient": False},  # sections
            {"answer": "still no", "confidence": "low", "sufficient": False},  # the page in full
            {"answer": "Now I can answer.", "confidence": "high", "sufficient": True},  # round 2
        ],
    )
    result = answer_by_cascade("formula?", store=store, catalog=cat, llm=llm)
    cat.close()

    assert result.answer.status == "answered"
    assert result.rounds == 2
    assert len(result.basket) == 2  # it KEPT round 1's page and ADDED round 2's — nothing is lost


def test_nothing_in_the_library_is_an_honest_not_found(store, tmp_path):
    """P6. The librarian must be ABLE to say the library does not hold this — but only after the
    last resort has read the closest pages in full and the answerer still refuses them."""
    cat, placements, paths = _library(store, tmp_path, [PAGE, PAGE])
    llm = FakeLLM(
        placements,
        paths[0],
        basket=[[], []],
        answers=[{"answer": "nothing here", "confidence": "low", "sufficient": False}],
    )

    result = answer_by_cascade("how do I tune a turbocharger?", store=store, catalog=cat, llm=llm)
    cat.close()

    assert result.answer.status == "not_found"
    assert result.nav.status == "NOT_FOUND"
    assert not result.answer.citations  # never improvise


def test_it_never_declares_the_library_empty_while_holding_the_closest_pages(store, tmp_path):
    """The bug that cost the cascade its A/B: it gave up THREE times, and in TWO of those it had
    already reached the exact target page. The sieve found it, the triage basketed it, and the
    answerer still said "insufficient" — because it was handed one page where the walk would have
    handed it three (the walk's found_rate was 100%; ours was 90%).

    A librarian may not tell the reader the library holds nothing while the closest pages sit
    unread on his desk. Only after reading them in full is a NOT_FOUND honest (P6).
    """
    cat, placements, paths = _library(store, tmp_path, [PAGE] * 6)
    llm = FakeLLM(
        placements,
        target=paths[0],
        basket=[[], []],  # the librarian triages nothing, twice
        answers=[{"answer": "Here it is.", "confidence": "high", "sufficient": True}],
    )
    result = answer_by_cascade("formula?", store=store, catalog=cat, llm=llm)
    cat.close()

    assert result.answer.status == "answered"
    assert any("closest pages in full" in e.title for e in result.nav.events)
    assert result.nav.pages  # it read them rather than shrugging
    assert result.answer.citations  # …and it can still cite what it used


def test_a_genuine_not_found_survives_the_last_resort(store, tmp_path):
    """…but the last resort is not a licence to improvise. If the closest pages in full still do not
    answer, the honest NOT_FOUND stands (P6)."""
    cat, placements, paths = _library(store, tmp_path, [PAGE] * 6)
    llm = FakeLLM(
        placements,
        target=paths[0],
        basket=[[], []],
        answers=[{"answer": "no", "confidence": "low", "sufficient": False}],
    )
    result = answer_by_cascade("how do I tune a turbocharger?", store=store, catalog=cat, llm=llm)
    cat.close()

    assert result.answer.status == "not_found"
    assert not result.answer.citations  # never improvise
