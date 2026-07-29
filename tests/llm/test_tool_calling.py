"""LIVE tool-calling smoke tests. SPENDS TOKENS — `-m llm` only, never in the default suite.

These exist because D-067 removed a REFUSAL, not because it added a feature. Tool calling used to
raise on DashScope on the grounds that a cheap model fails at navigation (D-027). That argument is
about the walk; the pool tools (D-066) are a handful of bounded calls over candidates the sieve
already found. Removing a guard on an argument means the replacement has to be a measurement — so
these run the real protocol against the real provider.

What they check is the PROTOCOL, not the model's judgement:
  * does qwen-plus emit a tool call at all, with parseable arguments?
  * does the result round-trip — can we send the tool's answer back and get a second turn?
    (This is the half that fails silently: DashScope rejects the request AFTER the one with the
    missing `tool_call_id`, so a broken echo looks like a random failure a turn later.)

Cost: two or three short calls on qwen-plus. Pennies.

    .venv\\Scripts\\python.exe -m pytest tests/llm/test_tool_calling.py -m llm -v -s
"""

import pytest

from libkb.config import get_settings
from libkb.llm.client import LLM, ToolResponse, ToolSpec, Turn

pytestmark = pytest.mark.llm

WEATHER = ToolSpec(
    name="get_temperature",
    description="Return the current temperature in a city, in Celsius.",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
)


@pytest.fixture
def llm():
    if not get_settings().dashscope_api_key:
        pytest.skip("no DASHSCOPE_API_KEY in .env")
    return LLM()


def test_qwen_plus_emits_a_tool_call_with_parseable_arguments(llm):
    result = llm.generate(
        "What is the temperature in Hanoi right now? Use the tool.",
        model="qwen-plus",
        tools=[WEATHER],
    )
    print(f"\n  tool_calls={[(c.name, c.args, c.call_id) for c in result.tool_calls]}")
    assert result.tool_calls, "qwen-plus returned no tool call"
    call = result.tool_calls[0]
    assert call.name == "get_temperature"
    assert "hanoi" in str(call.args.get("city", "")).lower()
    assert call.call_id, "no call id — the result cannot be correlated on the next turn"
    assert result.text is None, "a turn that called a tool must not also read as an answer"


def test_the_result_round_trips_and_the_model_answers_from_it(llm):
    """The half that fails LATER if it fails: a missing `tool_call_id` is rejected on the NEXT
    request, so this is the only place the echo is actually proven."""
    first = llm.generate(
        "What is the temperature in Hanoi right now? Use the tool.",
        model="qwen-plus",
        tools=[WEATHER],
    )
    assert first.tool_calls, "cannot test the round trip without a first call"
    call = first.tool_calls[0]

    turns = [
        Turn(role="user", text="What is the temperature in Hanoi right now? Use the tool."),
        Turn(role="model", text=first.text, tool_calls=first.tool_calls),
        Turn(
            role="tool",
            tool_responses=[
                ToolResponse(
                    name=call.name, response={"celsius": 31, "city": "Hanoi"}, call_id=call.call_id
                )
            ],
        ),
    ]
    second = llm.generate(turns, model="qwen-plus", tools=[WEATHER])
    print(f"\n  second turn: {second.text!r}")
    assert second.text, "the model produced no answer after the tool result"
    assert "31" in second.text, "it did not use the value the tool returned"


def test_the_pool_agent_tools_are_accepted_as_a_schema(llm):
    """Our real specs, not a toy one — `select` has a nested array-of-objects, which is where an
    over-simple schema translation would break."""
    from libkb.agent.poolagent import TOOLS

    result = llm.generate(
        "You must call `coverage_map` first. Do it now.", model="qwen-plus", tools=TOOLS
    )
    print(f"\n  tool_calls={[c.name for c in result.tool_calls]}")
    assert result.tool_calls, "qwen-plus rejected or ignored the pool-agent tool schemas"


def test_gemini_still_works_the_same_way(llm):
    """The guard against fixing one provider by breaking the other."""
    result = llm.generate(
        "What is the temperature in Hanoi right now? Use the tool.",
        model=get_settings().model,
        tools=[WEATHER],
    )
    assert result.tool_calls and result.tool_calls[0].name == "get_temperature"
