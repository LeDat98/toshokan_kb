"""Tools over the candidate POOL, and the loop that uses them (D-066/D-067). All LLM-free.

The scope rule these encode: the sieve already found the evidence (FiQA R@100 0.920, MultiHop
AllGold@20 93.5%) and the SELECTOR loses it (69% vs the embedder's own 75%). So nothing here
retrieves. Everything here answers, over the 50–100 candidates already proposed, a question the
agent would otherwise guess at from a section title.

Two properties matter more than any single tool and are tested hardest:
  * **the pool is a fence** — no tool may reach a page outside it, and a model naming one is told
    so rather than quietly given a best guess;
  * **budgets are enforced in CODE** (D-008) — a model asked nicely to stop will not, and running
    out must close the loop out with a basket rather than lose the turn.
"""

import pytest

from libkb.agent.pooltools import (
    coverage_map,
    find_in_candidates,
    render_coverage,
    render_hits,
    split_question,
)
from libkb.config import get_settings
from libkb.library.models import PageContent
from libkb.llm.client import (
    ToolCall,
    ToolResponse,
    Turn,
    _dashscope_messages,
    _dashscope_tool_calls,
)

RETURNS = """# Return policy

## Deadline
A return must be lodged within 30 days of delivery.

## Restocking fee
A restocking fee of 15% applies to opened electronics. Reference code RF-15A.
"""

INTL = """# International orders

## Window
International orders carry a 60 day window instead of 30.
"""

TURBO = "# Turbochargers\n\nTurbochargers force air into an engine.\n"

POOL = [
    ("p_returns", "retail ▸ policies ▸ returns", RETURNS),
    ("p_intl", "retail ▸ policies ▸ intl", INTL),
    ("p_turbo", "auto ▸ engines ▸ turbo", TURBO),
]


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ------------------------------------------------------------------ splitting the question


def test_a_compound_question_splits_into_its_parts():
    """The measured multi-hop floor (comparison 74%, temporal 58%) is a coverage failure: one
    blurred query vector ranks no part sharply, and a pointwise selector cannot notice it covered
    the same half twice. Naming the parts is what makes coverage answerable at all."""
    parts = split_question("what is the restocking fee and how long do international orders have")
    assert len(parts) == 2
    assert "restocking fee" in parts[0]
    assert "international orders" in parts[1]


def test_a_single_fact_question_stays_one_part():
    assert split_question("what is the restocking fee") == ["what is the restocking fee"]


def test_splitting_never_returns_nothing():
    """A question of pure stopwords must degrade to itself, not to an empty part list — a coverage
    map over zero parts would silently claim every page covers everything."""
    assert split_question("and or but") == ["and or but"]
    assert split_question("?") == ["?"]


# ------------------------------------------------------------------ coverage_map


def test_coverage_map_says_which_page_covers_which_part():
    cov = coverage_map("restocking fee and international orders window", POOL)
    by_id = {c.page_id: c.covered for c in cov.cells}
    assert len(cov.parts) == 2
    assert by_id["p_returns"] == [0], "the returns page covers the fee part only"
    assert by_id["p_intl"] == [1], "the international page covers the window part only"
    assert by_id["p_turbo"] == [], "an unrelated page covers nothing"


def test_coverage_map_names_the_part_no_candidate_covers():
    """The honest signal the widen round currently has to infer."""
    cov = coverage_map("restocking fee and warranty claims for turbochargers abroad", POOL)
    assert cov.uncovered, "a part nothing covers must be reported, not silently dropped"


def test_a_page_needs_HALF_a_part_not_one_shared_word():
    """Threshold per part, never a sum across parts — summing is precisely how BM25 lets a crowd of
    common words bury the one document that answers (see tests/test_lexical.py)."""
    cov = coverage_map(
        "restocking fee", [("p", "path", "A fee is charged. Nothing about restocking.")]
    )
    assert cov.cells[0].covered == [0], "2 of 2 content words present ⇒ covered"
    cov2 = coverage_map(
        "restocking fee for opened electronics", [("p", "path", "The word fee appears here.")]
    )
    assert cov2.cells[0].covered == [], "one shared word out of four is not coverage"


def test_best_set_is_a_greedy_cover_not_a_top_k():
    """The point of set-selection: two pages that TOGETHER cover the question beat two pages that
    both cover its most obvious half."""
    cov = coverage_map("restocking fee and international orders window", POOL)
    assert set(cov.best_set(2)) == {"p_returns", "p_intl"}


def test_best_set_stops_when_everything_is_covered():
    cov = coverage_map("restocking fee and international orders window", POOL)
    assert len(cov.best_set(10)) == 2, "it must not pad the basket with pages that add nothing"


def test_render_coverage_is_silent_on_a_single_part_question():
    """A one-part question has no map; emitting an empty table spends the tokens the tool saves."""
    assert render_coverage(coverage_map("what is the restocking fee", POOL)) == ""


def test_render_coverage_lists_parts_and_the_hole():
    text = render_coverage(coverage_map("restocking fee and warranty claims abroad", POOL))
    assert "[1]" in text and "[2]" in text
    assert "NO candidate covers" in text


# ------------------------------------------------------------------ find_in_candidates


def test_find_locates_the_exact_term_and_names_its_section():
    """Naming the SECTION is half the tool: the agent's next move is to ask for one by name."""
    hits = find_in_candidates("RF-15A", POOL)
    assert len(hits) == 1
    assert hits[0].page_id == "p_returns"
    assert hits[0].section == "Restocking fee"
    assert "RF-15A" in hits[0].line


def test_find_is_case_insensitive_and_reports_nothing_honestly():
    assert find_in_candidates("rf-15a", POOL)
    assert find_in_candidates("GMROI", POOL) == []
    assert find_in_candidates("   ", POOL) == []


def test_a_broken_regex_degrades_to_a_literal_search_instead_of_crashing():
    """A model will eventually send `fee (unclosed`. One bad tool call must cost one call."""
    assert find_in_candidates("fee (unclosed", POOL, regex=True) == []
    hits = find_in_candidates("15%", POOL, regex=True)  # '%' is fine, but '15%' is not a regex op
    assert hits and hits[0].page_id == "p_returns"


def test_render_hits_says_so_when_nothing_matched():
    assert "Nothing in the candidates" in render_hits([], "GMROI")


# ------------------------------------------------------------------ the loop and its budgets


class _FakeStore:
    def __init__(self, pages):
        self._pages = {pid: md for pid, _, md in pages}
        self._paths = {pid: path for pid, path, _ in pages}

    def page(self, page_id):
        return PageContent(
            page_id=page_id, book_id="b", title=page_id, markdown=self._pages[page_id]
        )

    def path_str(self, page_id):
        return self._paths[page_id]


class _ScriptedLLM:
    """Replays a list of tool-call batches, then falls through to prose."""

    def __init__(self, script, json_replies=None):
        self.script = list(script)
        self.json_replies = list(json_replies or [])
        self.generate_calls = 0
        self.json_calls = 0

    def load_prompt(self, name, **kw):
        self.last_prompt = name
        return f"[{name}]"

    def generate(self, contents, *, tools=None, **kw):
        from libkb.llm.client import LLMResult

        self.generate_calls += 1
        if self.script:
            return LLMResult(text=None, tool_calls=self.script.pop(0))
        return LLMResult(text="I think page one.", tool_calls=[])

    def generate_json(self, contents, *, schema, model=None, **kw):
        self.json_calls += 1
        return self.json_replies.pop(0) if self.json_replies else {"answers": True, "quote": "q"}


def _hits():
    from libkb.catalog.store import Hit as CatalogHit

    return [
        CatalogHit(page_id=pid, book_id="b", path="", text="", lang="en", score=0.9)
        for pid, _, _ in POOL
    ]


def _agent(script, json_replies=None, **budget):
    from libkb.agent.poolagent import Budget, PoolAgent

    llm = _ScriptedLLM(script, json_replies)
    agent = PoolAgent(
        "restocking fee and international window",
        _hits(),
        _FakeStore(POOL),
        llm,
        get_settings(),
        max_pages=3,
        budget=Budget(**budget) if budget else None,
    )
    return agent, llm


def _call(name, **args):
    return ToolCall(name=name, args=args, call_id=f"c_{name}")


def test_select_ends_the_loop_and_returns_the_basket():
    agent, llm = _agent([[_call("select", pages=[{"page": "retail ▸ policies ▸ returns"}])]])
    result = agent.run()
    assert [s.page_id for s in result.selected] == ["p_returns"]
    assert result.tool_calls == ["select"]
    assert llm.generate_calls == 1


def test_a_tool_may_not_reach_a_page_outside_the_pool():
    """The fence. A model naming a page it was never shown is hallucinating, and the honest reply
    is 'that is not one of your candidates' — not a silent best guess at what it meant."""
    agent, _ = _agent(
        [
            [_call("read_section", page="secret ▸ payroll ▸ salaries")],
            [_call("select", pages=[{"page": "retail ▸ policies ▸ returns"}])],
        ]
    )
    result = agent.run()
    assert result.selected, "the loop continues after a rejected page"
    assert agent.budget.reads == 0, "a rejected page must not spend the read budget"


def test_the_step_budget_is_enforced_in_code_and_closes_out_with_a_basket():
    """A model asked nicely to stop will not. And running out must not lose the turn: the close-out
    asks ONCE for the basket — a librarian out of time still hands over what he found."""
    forever = [[_call("find_in_candidates", pattern="fee")] for _ in range(20)]
    agent, llm = _agent(forever, max_steps=3, max_lite_calls=3, max_reads=6)
    # the close-out reply is served after the script runs out of *its* batches
    llm.script = forever[:3] + [[_call("select", pages=[{"page": "retail ▸ policies ▸ intl"}])]]
    result = agent.run()
    assert agent.budget.steps == 3
    assert agent.budget.exhausted == "steps"
    assert [s.page_id for s in result.selected] == ["p_intl"], "closed out WITH a basket"


def test_the_lite_call_budget_caps_ask_page():
    """`ask_page` is the only tool that costs money, so it gets its own ceiling."""
    script = [
        [_call("ask_page", page="retail ▸ policies ▸ returns", question="fee?")] for _ in range(5)
    ]
    script.append([_call("select", pages=[{"page": "retail ▸ policies ▸ returns"}])])
    agent, llm = _agent(script, max_steps=10, max_lite_calls=2, max_reads=6)
    agent.run()
    assert llm.json_calls == 2, "the 3rd consult is refused by code, not by the prompt"
    assert agent.budget.exhausted == "lite_calls"


def test_the_read_budget_caps_context_growth():
    script = [[_call("read_section", page="retail ▸ policies ▸ returns", section="Deadline")]] * 5
    script.append([_call("select", pages=[{"page": "retail ▸ policies ▸ returns"}])])
    agent, _ = _agent(script, max_steps=10, max_lite_calls=3, max_reads=2)
    agent.run()
    assert agent.budget.reads == 2


def test_an_unknown_tool_name_is_answered_not_raised():
    agent, _ = _agent(
        [
            [_call("delete_everything", target="*")],
            [_call("select", pages=[{"page": "retail ▸ policies ▸ returns"}])],
        ]
    )
    assert agent.run().selected


def test_prose_instead_of_a_tool_call_triggers_the_close_out():
    """A model that answers in words has selected nothing. Keep its words, then ask properly."""
    agent, llm = _agent([])  # no tool calls at all → prose on the first turn
    llm.script = [[], [_call("select", pages=[{"page": "retail ▸ policies ▸ returns"}])]]

    from libkb.llm.client import LLMResult

    replies = [
        LLMResult(text="I think the returns page.", tool_calls=[]),
        LLMResult(
            text=None, tool_calls=[_call("select", pages=[{"page": "retail ▸ policies ▸ returns"}])]
        ),
    ]
    llm.generate = lambda *a, **kw: replies.pop(0)
    result = agent.run()
    assert result.thought.startswith("I think")
    assert [s.page_id for s in result.selected] == ["p_returns"]


def test_duplicate_picks_are_collapsed_and_the_cap_holds():
    agent, _ = _agent(
        [
            [
                _call(
                    "select",
                    pages=[
                        {"page": "retail ▸ policies ▸ returns"},
                        {"page": "retail ▸ policies ▸ returns"},
                        {"page": "retail ▸ policies ▸ intl"},
                    ],
                )
            ]
        ]
    )
    assert [s.page_id for s in agent.run().selected] == ["p_returns", "p_intl"]


def test_an_empty_pool_returns_empty_without_calling_the_model():
    from libkb.agent.poolagent import PoolAgent

    llm = _ScriptedLLM([])
    agent = PoolAgent("q", [], _FakeStore(POOL), llm, get_settings(), max_pages=3)
    assert agent.run().selected == []
    assert llm.generate_calls == 0


# ------------------------------------------------------------------ DashScope tool plumbing


def test_a_tool_call_turn_becomes_an_openai_assistant_message_with_ids():
    """Omit `tool_call_id` and DashScope 400s the NEXT request, not this one — which reads as a
    random failure several turns later. The round-trip is closed in the client, not per caller."""
    msgs = _dashscope_messages(
        Turn(role="model", text=None, tool_calls=[ToolCall("find", {"pattern": "x"}, call_id="c1")])
    )
    assert len(msgs) == 1
    assert msgs[0]["role"] == "assistant"
    assert msgs[0]["tool_calls"][0]["id"] == "c1"
    assert msgs[0]["tool_calls"][0]["function"]["arguments"] == '{"pattern": "x"}'


def test_several_tool_results_in_one_turn_fan_out_to_several_messages():
    """OpenAI wants one message per result; the loop batches them into a single Turn."""
    msgs = _dashscope_messages(
        Turn(
            role="tool",
            tool_responses=[
                ToolResponse("find", {"result": "a"}, call_id="c1"),
                ToolResponse("coverage_map", {"result": "b"}, call_id="c2"),
            ],
        )
    )
    assert [m["tool_call_id"] for m in msgs] == ["c1", "c2"]
    assert all(m["role"] == "tool" for m in msgs)


def test_a_plain_turn_still_maps_to_one_message():
    assert _dashscope_messages(Turn(role="user", text="hi")) == [{"role": "user", "content": "hi"}]
    assert _dashscope_messages(Turn(role="model", text="ok"))[0]["role"] == "assistant"


def test_malformed_tool_arguments_cost_one_call_not_the_loop():
    """Qwen does not enforce a schema server-side (D-040 was exactly this class of defect)."""

    class _Fn:
        def __init__(self, name, arguments):
            self.name, self.arguments = name, arguments

    class _Raw:
        def __init__(self, id, fn):
            self.id, self.function = id, fn

    class _Msg:
        tool_calls = [_Raw("c1", _Fn("find", "{not json")), _Raw("c2", _Fn("ok", '{"a": 1}'))]

    calls = _dashscope_tool_calls(_Msg())
    assert calls[0].args == {}, "a broken payload degrades to empty args"
    assert calls[1].args == {"a": 1}
    assert [c.call_id for c in calls] == ["c1", "c2"]


def test_a_message_with_no_tool_calls_yields_none():
    class _Msg:
        tool_calls = None

    assert _dashscope_tool_calls(_Msg()) == []
