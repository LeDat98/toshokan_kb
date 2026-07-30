"""The selection layer — the agent's ability to CHOOSE the right pages. All LLM-free.

The measured problem these tests encode (probe 2c, MultiHop n=150): the LLM triage keeps **69%** of
the gold, and just taking the embedder's top-10 keeps **75%**. The selector loses to the sieve.

A cross-encoder reranker was the obvious fix and it was measured and REFUTED (D-048). So what is
under test here is NOT a better ranker. It is the two axes a reranker never touched:

    the CARD    the selector chose on ~59 tokens of bare section titles → give it query-relevant
                passages and mark the sections whose text actually overlaps (`triage_card=rich`)
    the ASK     "is this page relevant?" one page at a time → "which pages TOGETHER cover this?"
                (`triage_mode=set`), where every pick must state what it adds

Both are computed or asked for free on a call we already make, and both are verifiable without a
model — which is what these tests do.
"""

import pytest

from libkb.agent.cascade import _cards, _triage_set, build_card
from libkb.agent.roles.librarian import selector_for
from libkb.catalog.store import Hit
from libkb.config import get_settings
from libkb.evals.selection import ARMS, DEFAULT_ARMS, ArmRow, Pools, SelQuery, run_arm
from libkb.library.models import PageContent
from libkb.library.sections import query_passages, query_snippet, relevant_sections

PAGE = """# Return policy

Refunds are issued to the original payment method.

## Deadline
A return must be lodged within 30 days of delivery.

## International orders
International orders carry a 60 day window instead of 30.

## Restocking fee
A restocking fee of 15% applies to opened electronics.
"""


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ------------------------------------------------------------------ passages & section relevance


def test_query_passages_returns_k_best_spans_in_score_order():
    spans = query_passages(PAGE, "restocking fee on international orders", k=2)
    assert len(spans) == 2
    assert "International orders carry a 60 day window" in " ".join(spans)
    assert "restocking fee of 15%" in " ".join(spans)


def test_query_passages_skips_headings_which_the_card_already_lists():
    """`## International orders` quoted back as 'the relevant passage' spends tokens to say nothing
    — it is already on the card under Sections. Containment-based dedup used to let that two-word
    heading SWALLOW the sentence underneath it, which is exactly backwards."""
    spans = query_passages(PAGE, "international orders", k=2)
    assert spans and spans[0].startswith("International orders carry")
    assert "International orders" not in [s.strip() for s in spans]


def test_query_passages_is_the_multi_part_lever():
    """The point of k>1: one span is by construction about the question's most obvious half."""
    one = query_passages(PAGE, "restocking fee on a late international return", k=1)
    many = query_passages(PAGE, "restocking fee on a late international return", k=3)
    assert len(one) == 1 and len(many) == 3
    joined = " ".join(many)
    assert "restocking fee" in joined.lower() and "International" in joined


def test_query_passages_deduplicates_near_identical_spans():
    repeated = "Turnover is COGS over average inventory.\n" * 5 + "\nThe formula excludes freight."
    spans = query_passages(repeated, "turnover formula COGS inventory", k=3)
    assert len(spans) < 3, "a page repeating its thesis must not spend the whole card on it"


def test_query_passages_honours_the_off_switches_and_the_no_overlap_case():
    assert query_passages(PAGE, "turbocharger", k=3) == []
    assert query_passages(PAGE, "deadline", k=0) == []
    assert query_passages(PAGE, "deadline", k=3, max_chars=0) == []


def test_query_snippet_is_bit_identical_to_the_measured_d050_behaviour():
    """D-050 is shipped and MEASURED (+1.7 answer, 2 seeds × n=200). Refactoring it onto
    query_passages must not change it — including the heading it used to be allowed to return.
    A shipped baseline that quietly improves is a baseline you can no longer compare against."""
    assert (
        query_snippet(PAGE, "deadline for international orders")
        == query_passages(PAGE, "deadline for international orders", k=1, skip_headings=False)[0]
    )
    # the shipped snippet hands back the bare HEADING here; the new path hands back the sentence
    # under it. That difference is the Tier-0 lever, and it must be measured, not assumed.
    assert query_snippet(PAGE, "international orders") == "International orders"
    assert query_passages(PAGE, "international orders", k=1)[0].startswith(
        "International orders carry"
    )
    assert query_snippet(PAGE, "turbocharger") == ""


def test_query_snippet_truncates_to_max_chars():
    long_page = "The deadline for a return is " + "very " * 100 + "soon."
    assert len(query_snippet(long_page, "deadline return", max_chars=40)) <= 40


def test_relevant_sections_names_the_section_whose_body_matches():
    assert relevant_sections(PAGE, "restocking fee for opened electronics", k=1) == [
        "Restocking fee"
    ]
    # a title can be uninformative while its body is the match — that is the whole point
    assert "International orders" in relevant_sections(PAGE, "60 day window", k=2)
    assert relevant_sections(PAGE, "turbocharger") == []


# ------------------------------------------------------------------ the card


class _FakeStore:
    """The three things `_cards` asks of a store. Small on purpose: a card is a pure function of a
    page and a query, and testing it should not need a library on disk."""

    def __init__(self, pages: dict[str, str], one_lines: dict[str, str] | None = None):
        self._pages = pages
        self._one_lines = one_lines or {}

    def page(self, page_id):
        return PageContent(
            page_id=page_id, book_id="b1", title=page_id, markdown=self._pages[page_id]
        )

    def toc_entry(self, page_id):
        return type("E", (), {"one_line": self._one_lines.get(page_id, "")})()

    def path_str(self, page_id):
        return f"retail ▸ policies ▸ {page_id}"


def _hit(page_id, text="", score=0.9):
    return Hit(page_id=page_id, book_id="b1", path="", text=text, lang="en", score=score)


def _settings(**over):
    return get_settings().model_copy(update=over)


QUERY = "restocking fee for international orders"


def test_lean_card_is_unchanged_titles_only():
    card = build_card(
        QUERY, _hit("returns"), _FakeStore({"returns": PAGE}).page("returns"), "", "p", _settings()
    )
    assert "Relevant passage:" in card  # a TEXT row has no display text → D-050 fires
    assert "  also:" not in card
    assert "▸" not in card, "lean must not mark sections — that is the rich card's lever"
    assert card.count("  - ") == 4


def test_rich_card_adds_passages_and_marks_the_matching_sections():
    card = build_card(
        QUERY,
        _hit("returns"),
        _FakeStore({"returns": PAGE}).page("returns"),
        "",
        "p",
        _settings(triage_card="rich", triage_passages=3),
    )
    assert "  also:" in card, "rich must show more than one passage"
    assert "▸ International orders" in card, "the section whose BODY matches must be marked"
    assert "▸ Restocking fee" in card, "the question's OTHER part must be marked too"
    assert "- Deadline" in card, "an unrelated section stays listed but unmarked, never hidden"
    assert "(▸ = its text overlaps your question)" in card


def test_rich_card_shows_the_passage_even_when_the_catalog_row_matched():
    """The lean card makes these mutually exclusive for no reason: 'what is this page FOR' and
    'what does it say about YOUR question' are different facts, and the selector wants both."""
    hit = _hit("returns", text="How long do I have to return something?")
    lean = build_card(
        QUERY, hit, _FakeStore({"returns": PAGE}).page("returns"), "", "p", _settings()
    )
    rich = build_card(
        QUERY,
        hit,
        _FakeStore({"returns": PAGE}).page("returns"),
        "",
        "p",
        _settings(triage_card="rich"),
    )
    assert "Answers questions like:" in lean and "Relevant passage:" not in lean
    assert "Answers questions like:" in rich and "Relevant passage:" in rich


def test_card_survives_a_page_with_no_sections():
    card = build_card(
        QUERY,
        _hit("flat"),
        _FakeStore({"flat": "Just a paragraph."}).page("flat"),
        "",
        "p",
        _settings(triage_card="rich"),
    )
    assert "Sections: (none — ask for the whole page)" in card


def test_cards_skips_a_stale_catalog_row_instead_of_crashing():
    class _Missing(_FakeStore):
        def page(self, page_id):
            from libkb.exceptions import NodeNotFound

            if page_id == "gone":
                raise NodeNotFound("gone")
            return super().page(page_id)

    cards, by_path = _cards(
        QUERY, [_hit("gone"), _hit("returns")], _Missing({"returns": PAGE}), _settings()
    )
    assert len(cards) == 1 and len(by_path) == 1


# ------------------------------------------------------------------ the set selector


class _SetLLM:
    """Returns a scripted set-selection reply and records the prompt it was given."""

    def __init__(self, reply):
        self.reply = reply
        self.kwargs = {}

    def load_prompt(self, name, **kw):
        self.name, self.kwargs = name, kw
        return f"[{name}]"

    def generate_json(self, contents, *, schema, model=None, **kw):
        self.schema = schema
        return self.reply


def _set_pick(reply, batch=None, max_pages=5, store=None):
    llm = _SetLLM(reply)
    picked, thought = _triage_set(
        QUERY,
        batch or [_hit("returns"), _hit("intl")],
        store or _FakeStore({"returns": PAGE, "intl": PAGE}),
        llm,
        _settings(),
        max_pages,
    )
    return picked, thought, llm


def test_set_selector_keeps_section_naming_and_the_contribution():
    picked, _, llm = _set_pick(
        {
            "thought": "Taking both — neither covers the whole question.",
            "selected": [
                {
                    "page": "retail ▸ policies ▸ returns",
                    "sections": ["Deadline"],
                    "contributes": "the 30-day rule",
                },
                {
                    "page": "retail ▸ policies ▸ intl",
                    "sections": [],
                    "contributes": "the 60-day exception",
                },
            ],
        }
    )
    assert llm.name == "select_set"
    assert [p.page_id for p in picked] == ["returns", "intl"]
    assert picked[0].sections == ["Deadline"], (
        "section naming must survive (D-053: whole-page picks lost)"
    )
    assert picked[0].why == "the 30-day rule"


def test_set_selector_surfaces_the_hole_it_could_not_fill():
    """`missing` is the signal the widen round currently has to infer — free on a call we make."""
    _, thought, _ = _set_pick(
        {"thought": "Only the deadline is here.", "selected": [], "missing": "the restocking fee"}
    )
    assert "still missing: the restocking fee" in thought


def test_set_selector_deduplicates_and_respects_the_basket_cap():
    picked, _, _ = _set_pick(
        {
            "selected": [
                {"page": "retail ▸ policies ▸ returns"},
                {"page": "retail ▸ policies ▸ returns"},  # the same page twice
                {"page": "retail ▸ policies ▸ intl"},
            ]
        },
        max_pages=2,
    )
    assert [p.page_id for p in picked] == ["returns"]


def test_set_selector_tolerates_a_null_selection_and_a_bad_path():
    """Qwen returns `{"selected": null}` for 'nothing here' — a required key can still be null."""
    assert _set_pick({"selected": None})[0] == []
    assert _set_pick({"selected": [{"page": "a page that does not exist"}]})[0] == []


def test_set_selector_is_given_the_same_cards_as_headers_triage():
    """The arms must differ by the QUESTION asked, not by the evidence shown, or the experiment
    measures two things at once."""
    _, _, llm = _set_pick({"selected": []})
    cards, _ = _cards(
        QUERY,
        [_hit("returns"), _hit("intl")],
        _FakeStore({"returns": PAGE, "intl": PAGE}),
        _settings(),
    )
    assert llm.kwargs["candidates"] == "\n\n".join(cards)


# ------------------------------------------------------------------ dispatch & the probe


def test_selector_for_maps_every_configured_mode():
    from libkb.agent.cascade import _triage, _triage_read
    from libkb.agent.cascade import _triage_set as _ts

    assert selector_for("headers") is _triage
    assert selector_for("read") is _triage_read
    assert selector_for("set") is _ts
    assert selector_for("nonsense") is _triage, "an unknown mode must fail SAFE, to the shipped one"


def test_cli_arm_names_do_not_drift_from_the_probe():
    from libkb.cli import _SEL_ARMS, _SEL_DEFAULT_ARMS

    assert tuple(ARMS) == _SEL_ARMS
    assert _SEL_DEFAULT_ARMS == DEFAULT_ARMS


def _pools(gold_per_query, pool_keys, basket=2):
    """Two queries, hand-built pools; page id == gold key so the mapping is the identity."""
    queries = [SelQuery(f"q{i}", "comparison_query", set(g)) for i, g in enumerate(gold_per_query)]
    ranked = [[_hit(k, score=1.0 - j / 10) for j, k in enumerate(keys)] for keys in pool_keys]
    return Pools(queries=queries, ranked=ranked, fetch_n=10, basket=basket)


def test_embedder_arm_takes_the_top_of_the_pool_and_spends_nothing():
    pools = _pools([{"A"}, {"B"}], [["A", "X"], ["X", "B"]], basket=1)
    rows = run_arm(
        "embedder", pools, store=None, key_of={k: k for k in "ABX"}, llm=_NoLLM(), workers=1
    )
    row = next(r for r in rows if r.kind == "all")
    assert row.calls == 0 and row.n == 2
    assert row.picked == 1.0
    assert row.allgold == 0.5, "basket=1 takes A (gold) for q0 and X (not gold) for q1"


def test_retention_is_scored_against_the_pool_not_the_whole_corpus():
    """The thesis metric: of the gold the sieve ALREADY found, how much did the selector keep? A
    query whose gold was never in the pool is a SIEVE failure and must not be charged to the
    selector — it is excluded from retention and shows up in `ceiling` instead."""
    # q0: gold {A,B}, pool has both → a basket of 2 can keep both.
    # q1: gold {C,D}, pool has only C → ceiling is 0.5; keeping C is retention 1.0, not 0.5.
    pools = _pools([{"A", "B"}, {"C", "D"}], [["A", "B"], ["C", "Z"]], basket=2)
    rows = run_arm(
        "embedder", pools, store=None, key_of={k: k for k in "ABCDZ"}, llm=_NoLLM(), workers=1
    )
    row = next(r for r in rows if r.kind == "all")
    assert row.retention == 1.0, "the selector threw nothing away"
    assert row.coverage == pytest.approx(0.75)  # 1.0 and 0.5
    assert row.ceiling == pytest.approx(0.75), "the pool itself capped q1 at half its gold"
    assert row.allgold == 0.5 and row.ceiling_allgold == 0.5


def test_a_selector_that_throws_gold_away_scores_below_the_embedder(monkeypatch):
    """The shape of the finding this probe exists to detect — an ARM that loses to doing nothing."""
    import libkb.agent.roles.librarian as lib

    def _drops_everything(query, batch, store, llm, s, max_pages):
        return [], ""

    monkeypatch.setattr(lib, "selector_for", lambda mode: _drops_everything)
    pools = _pools([{"A", "B"}], [["A", "B"]], basket=2)
    key_of = {k: k for k in "AB"}
    passive = next(
        r
        for r in run_arm("embedder", pools, store=None, key_of=key_of, llm=_NoLLM(), workers=1)
        if r.kind == "all"
    )
    active = next(
        r
        for r in run_arm("headers", pools, store=None, key_of=key_of, llm=_NoLLM(), workers=1)
        if r.kind == "all"
    )
    assert passive.retention == 1.0 and active.retention == 0.0
    assert active.empty == 1, "an empty basket is the D-035 failure and gets its own column"


def test_a_selector_that_raises_drops_the_row_rather_than_scoring_it_zero(monkeypatch):
    """A transport error is evidence of nothing. Scoring it as 'the agent chose nothing' would be a
    claim about the mechanism — the exact mistake the eval already refuses to make elsewhere."""
    import libkb.agent.roles.librarian as lib

    def _boom(*a, **kw):
        raise RuntimeError("socket died")

    monkeypatch.setattr(lib, "selector_for", lambda mode: _boom)
    pools = _pools([{"A"}, {"B"}], [["A"], ["B"]], basket=2)
    rows = run_arm(
        "headers", pools, store=None, key_of={"A": "A", "B": "B"}, llm=_NoLLM(), workers=1
    )
    row = next(r for r in rows if r.kind == "all")
    assert row.n == 0 and row.calls == 0


class _NoLLM:
    total_input_tokens = 0
    total_output_tokens = 0


def test_the_free_size_arms_spend_nothing_and_choose_their_own_basket():
    """`adaptive` and `conformal` never call a model, and — unlike `embedder` — they are NOT bound
    by `pools.basket`: choosing the size IS what they do. TP is 2-4 and varies; a fixed basket
    cannot be a superset of a moving target."""
    pools = _pools([{"A"}, {"B"}], [["A", "X", "Y"], ["X", "B", "Y"]], basket=1)
    key_of = {k: k for k in "ABXY"}
    for arm in ("adaptive", "conformal"):
        row = next(
            r
            for r in run_arm(arm, pools, store=None, key_of=key_of, llm=_NoLLM(), workers=1)
            if r.kind == "all"
        )
        assert row.calls == 0, f"{arm} must be free"
        assert row.input_tokens == 0 and row.output_tokens == 0
        assert row.picked > 1, f"{arm} must be free to exceed basket=1"


def test_conformal_is_calibrated_before_the_pool_is_scored_not_inside_it():
    """The leakage guard at arm level: `conformal_thresholds` reads gold, so it must be computed
    once, up front, for the whole arm — never per query inside the scoring pass."""
    from libkb.evals.selection import conformal_thresholds, gold_ranks

    pools = _pools([{"A"}, {"B"}], [["X", "A"], ["B", "Y"]], basket=2)
    key_of = {k: k for k in "ABXY"}
    assert gold_ranks(pools, key_of, 0) == [1], "gold sits at rank 1 in its own pool"
    assert gold_ranks(pools, key_of, 1) == [0]
    thresholds = conformal_thresholds(pools, key_of, alpha=0.1, folds=2, seed=1)
    assert len(thresholds) == 2


def test_a_gold_document_missing_from_the_pool_is_a_ceiling_failure_not_a_threshold_one():
    from libkb.evals.selection import gold_ranks

    pools = _pools([{"A", "Z"}], [["A", "X"]], basket=2)
    assert gold_ranks(pools, {"A": "A", "X": "X"}, 0) is None


def test_the_matched_control_runs_the_embedder_at_the_same_page_count():
    """Rule 2 of docs/SELECTION_TARGET.md, enforced in code: an adaptive arm is only better if it
    beats the embedder TAKING THE SAME NUMBER OF PAGES. Across `taken` is metric bug 6.8."""
    from libkb.evals.selection import matched_control

    pools = _pools([{"A"}], [["X", "Y", "A", "Z"]], basket=1)
    ctrl = matched_control(3.0, pools, store=None, key_of={k: k for k in "AXYZ"}, llm=_NoLLM())
    assert ctrl is not None
    assert ctrl.taken == 3.0, "the control must commit to the same number of DOCUMENTS"
    assert ctrl.calls == 0, "the control is free — there is no excuse for skipping it"
    assert pools.basket == 1, "the control must not mutate the shared pools"


def test_the_matched_control_searches_the_basket_because_pages_are_not_documents():
    """A basket is counted in PAGES and `taken` in DOCUMENTS. Here two pages belong to one article,
    so a basket of 3 pages commits to only 2 documents — matching the two numbers directly is the
    same category error rule 2 exists to prevent."""
    from libkb.evals.selection import matched_control

    pools = _pools([{"A"}], [["a1", "a2", "B", "C", "D"]], basket=1)
    key_of = {"a1": "A", "a2": "A", "B": "B", "C": "C", "D": "D"}
    ctrl = matched_control(3.0, pools, store=None, key_of=key_of, llm=_NoLLM())
    assert ctrl is not None and ctrl.taken == 3.0
    assert ctrl.picked == 4.0, "it had to take FOUR pages to reach three documents"
    assert ctrl.arm == "embedder@4"


def test_arm_row_reports_per_kind_so_multi_document_kinds_are_visible():
    pools = _pools([{"A"}], [["A"]], basket=1)
    pools.queries[0].kind = "temporal_query"
    rows = run_arm("embedder", pools, store=None, key_of={"A": "A"}, llm=_NoLLM(), workers=1)
    assert {r.kind for r in rows} == {"all", "temporal_query"}
    assert all(isinstance(r, ArmRow) for r in rows)
