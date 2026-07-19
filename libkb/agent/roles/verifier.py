"""The Verifier role — code-checked anti-fabrication (D-057), exposed as a generic capability agent.

Unlike the Librarian/Answerer, the Verifier is pure and stateless — text in, verdict out — so it is
a real generically-dispatchable `CapabilityAgent`: the `run(payload) -> dict` shape an MCP tool or
an external A2A agent speaks. The answerer already runs this check inline; registering it as an
agent makes the capability discoverable and reusable by future agents.
"""

from __future__ import annotations

from libkb.agent.roles.base import AgentCard, EmitFn


class VerifierAgent:
    card = AgentCard(
        id="verifier",
        name="Verifier",
        description="Checks, in code, that every figure asserted in an answer appears in the "
        "evidence. Model-independent anti-fabrication (D-057).",
        skills=["verify-numbers"],
        input_schema={"answer": "string", "evidence": "string"},
        output_schema={"invented": "string[]", "ok": "boolean"},
        dispatchable=True,
    )

    def run(self, payload: dict, emit: EmitFn | None = None) -> dict:
        from libkb.agent.answerer import _invented_figures, _norm

        answer = str(payload.get("answer") or "")
        evidence = str(payload.get("evidence") or "")
        invented = _invented_figures(answer, _norm(evidence))
        return {"invented": invented, "ok": not invented}
