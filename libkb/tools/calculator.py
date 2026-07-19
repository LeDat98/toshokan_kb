"""A calculator SKILL + ROUTE (Phase C.2, D-061) — the first tool the model uses, cost-gated by the
router: it only runs when the orchestrator routes a COMPUTE request here.

Deterministic on purpose. The model extracts an arithmetic expression, but a SAFE evaluator (an AST
walk over numbers and + - * / ** % (), never `eval()`) computes it — so a number in the answer is
computed, not guessed. That IMPROVES honesty: it removes exactly the mental-math fabrication D-057
fights, and it cannot execute arbitrary code from a model (or an injected page).
"""

from __future__ import annotations

import ast
import operator

from libkb.agent.answerer import Answer
from libkb.agent.navigator import NavResult
from libkb.agent.roles.base import AgentCard, EmitFn
from libkb.agent.roles.routes import RouteContext
from libkb.agent.tools import NavEvent
from libkb.llm.client import get_llm

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(expr: str) -> float:
    """Evaluate a pure-arithmetic expression: numbers and + - * / // % ** and parentheses only.
    Raises ValueError on anything else (names, calls, attributes) — no code ever runs."""
    return _ev(ast.parse(expr, mode="eval").body)


def _ev(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_ev(node.left), _ev(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_ev(node.operand))
    raise ValueError("only numbers and + - * / // % ** () are allowed")


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{round(x, 6):g}"


class CalculatorAgent:
    """The calculator as a dispatchable tool (A2A/MCP shape): `{expression}` in, `{result}` out.
    The same tool a real MCP server would expose; here it is local and deterministic."""

    card = AgentCard(
        id="tool:calculator",
        name="Calculator",
        description="Evaluate an arithmetic expression safely (numbers and + - * / // % ** only).",
        skills=["tool", "math"],
        input_schema={"expression": "string"},
        output_schema={"result": "number"},
        dispatchable=True,
    )

    def run(self, payload: dict, emit: EmitFn | None = None) -> dict:
        return {"result": safe_eval(str(payload.get("expression") or ""))}


_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {"expression": {"type": "string"}, "explain": {"type": "string"}},
    "required": ["expression"],
}


class CalculatorRoute:
    """The `calculator` front-door route (D-061): the orchestrator sends COMPUTE requests here. It
    extracts an expression with one lite call, computes it deterministically, and answers — or
    returns None to defer to the library if the message is not actually a calculation."""

    card = AgentCard(
        id="calculator",
        name="Calculator",
        description="Computes arithmetic the reader asks for — sums, products, percentages, ratios "
        "— deterministically, never by guessing.",
        skills=["math", "compute"],
        route_when="a request to COMPUTE something arithmetic (a sum, product, percentage, ratio, "
        "or simple conversion), e.g. 'what is 15% of 240?'",
    )
    _calc = CalculatorAgent()

    def handle(self, ctx: RouteContext) -> tuple[Answer, NavResult] | None:
        llm = ctx.llm or get_llm()
        prompt = llm.load_prompt("calc_extract", query=ctx.query)
        try:
            data = llm.generate_json(prompt, schema=_EXTRACT_SCHEMA, model=ctx.settings.model_lite)
            expr = str(data.get("expression") or "").strip()
            if not expr:
                return None  # not a calculation — let the library handle it
            result = self._calc.run({"expression": expr})["result"]
            explain = str(data.get("explain") or "").strip()
        except Exception:
            return None  # couldn't parse/compute — defer to the library rather than fabricate
        text = f"{expr} = {_fmt(result)}"
        if explain:
            text = f"{explain}: {text}"
        events = [
            NavEvent(
                "thought",
                "This is a computation — using the calculator.",
                None,
                None,
                "done",
                detail="route",
            ),
            NavEvent("found", "computed", None, None, "found", detail="calculator"),
        ]
        if ctx.emit:
            for ev in events:
                ctx.emit(ev)
        answer = Answer(text=text, status="answered", confidence="high")
        return answer, NavResult(status="FOUND", reason="calculator", events=events)
