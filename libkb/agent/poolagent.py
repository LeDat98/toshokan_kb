"""A ReAct loop the agent runs OVER THE CANDIDATE POOL — the tool-calling form of D-066.

`_triage_trace` hands the agent a coverage map it did not ask for. This goes the other way: the
agent is given TOOLS and decides for itself what to look up before committing to a basket. The
tools are the same pool-scoped ones (`pooltools`) plus one that costs a cheap call:

    find_in_candidates(pattern)   0 LLM   which candidates literally contain this phrase, and where
    coverage_map()               0 LLM   which candidate covers which part of the question
    read_section(page, section)  0 LLM   the actual text of one section
    ask_page(page, question)     1 lite  "does THIS page answer it? quote the line" — verification
    select(pages)                  —     commit; ends the loop

**Why this is not the walk.** The walk (9–13 calls, O(T²), refuted as the default in D-036) searched
a TREE: a wrong turn at depth 1 was unrecoverable and every turn resent the whole conversation. This
loop cannot get lost — the candidate set is fixed at 50–100 before it starts, every tool answers
from that set, and the worst outcome of a bad tool call is one wasted step. What it buys is the
thing the measurement keeps pointing at: the selector currently guesses from titles, and 24 points
of gold die there.

**The budget is enforced HERE, in code, never in the prompt** (the project's standing rule, D-008).
A model asked nicely to stop after six steps will not. Three independent ceilings:

    max_steps       tool-calling rounds before the loop is closed out
    max_lite_calls  `ask_page` calls — the only tool that costs money
    max_reads       sections read, so context cannot grow without bound

When a budget runs out the loop does not fail: it asks once, plainly, for the basket. **A librarian
out of time still hands over what he found.** And if even that produces nothing, the caller falls
back to the shipped triage — an agent that spent its budget learning nothing must not also cost the
reader the answer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

from libkb.agent.pooltools import (
    coverage_map,
    find_in_candidates,
    render_coverage,
    render_hits,
)
from libkb.catalog.store import Hit
from libkb.config import Settings
from libkb.exceptions import LLMError, NodeNotFound
from libkb.library.sections import pick_sections
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, ToolCall, ToolResponse, ToolSpec, Turn

log = structlog.get_logger(__name__)

# An instrumentation seam, not a feature. The probe needs to know WHICH TOOLS the agent chose per
# question — "does it route adaptively?" is the question the loop exists to answer, and a score
# alone cannot answer it. Default None ⇒ zero cost and no behaviour change in production.
OBSERVER: Callable[[PoolResult, str], None] | None = None

_ANSWERS_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {"type": "boolean"},
        "quote": {"type": "string"},
    },
    "required": ["answers"],
}

TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="find_in_candidates",
        description=(
            "Search the candidate pages for an exact word or phrase. Use it for anything that "
            "appears VERBATIM — a number, a code, a name, a defined term. Returns the pages and "
            "the section inside each where it occurs. Free; call it as often as you like."
        ),
        parameters={
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"],
        },
    ),
    ToolSpec(
        name="coverage_map",
        description=(
            "Break the question into its parts and show which candidate covers which part, "
            "computed from the page text. Use it first on any question with more than one part "
            "('compare A and B', 'what changed, and does it apply to X'). Free."
        ),
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="read_section",
        description=(
            "Read one section of one candidate. Use it when a page looks right but you need to "
            "check before committing. Free."
        ),
        parameters={
            "type": "object",
            "properties": {"page": {"type": "string"}, "section": {"type": "string"}},
            "required": ["page"],
        },
    ),
    ToolSpec(
        name="ask_page",
        description=(
            "Ask whether ONE page actually answers a question, and get the supporting quote. "
            "Costs a call — use it to settle a case you cannot settle by reading."
        ),
        parameters={
            "type": "object",
            "properties": {"page": {"type": "string"}, "question": {"type": "string"}},
            "required": ["page", "question"],
        },
    ),
    ToolSpec(
        name="select",
        description=(
            "Commit: the pages the answerer should open, best first. Name sections when you are "
            "sure which hold the answer, otherwise leave them out and the whole page is opened."
        ),
        parameters={
            "type": "object",
            "properties": {
                "pages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "page": {"type": "string"},
                            "sections": {"type": "array", "items": {"type": "string"}},
                            "why": {"type": "string"},
                        },
                        "required": ["page"],
                    },
                },
                "missing": {"type": "string"},
            },
            "required": ["pages"],
        },
    ),
]


@dataclass
class Budget:
    """Ceilings, and what was actually spent. Reported so a run can be priced and so "the agent
    ran out of budget" is visible in the trace rather than inferred from a short basket."""

    max_steps: int = 6
    max_lite_calls: int = 3
    max_reads: int = 6
    steps: int = 0
    lite_calls: int = 0
    reads: int = 0
    exhausted: str = ""  # which ceiling ended the loop, if any

    def spend_step(self) -> bool:
        self.steps += 1
        if self.steps >= self.max_steps:
            self.exhausted = self.exhausted or "steps"
            return False
        return True


@dataclass
class Selection:
    page_id: str
    sections: list[str] = field(default_factory=list)
    why: str = ""


@dataclass
class PoolResult:
    selected: list[Selection] = field(default_factory=list)
    thought: str = ""
    missing: str = ""
    budget: Budget = field(default_factory=Budget)
    tool_calls: list[str] = field(default_factory=list)  # names, in order — the trace


class PoolAgent:
    """Runs the loop. One instance per query: it holds the pool, so a tool cannot reach past it."""

    def __init__(
        self,
        query: str,
        batch: list[Hit],
        store: LibraryStore,
        llm: LLM,
        settings: Settings,
        max_pages: int,
        budget: Budget | None = None,
    ) -> None:
        self.query = query
        self.store = store
        self.llm = llm
        self.s = settings
        self.max_pages = max_pages
        self.budget = budget or Budget(
            max_steps=settings.pool_max_steps,
            max_lite_calls=settings.pool_max_lite_calls,
            max_reads=settings.pool_max_reads,
        )
        self.result = PoolResult(budget=self.budget)
        # The pool, resolved ONCE. Every tool reads from here — that is what makes this loop
        # bounded rather than a walk: there is no operation that can reach a page outside it.
        self.pages: list[tuple[str, str, str]] = []
        self.by_path: dict[str, str] = {}
        for hit in batch:
            try:
                markdown = store.page(hit.page_id).markdown
            except NodeNotFound:
                continue  # a stale catalog row must not break a query
            path = store.path_str(hit.page_id)
            self.pages.append((hit.page_id, path, markdown))
            self.by_path[path] = hit.page_id

    # ---------------------------------------------------------------- tools

    def _resolve(self, name: str) -> str | None:
        """A path (or a near-miss of one) → a page_id, restricted to the pool. Returns None for
        anything outside it: a model naming a page it was never shown is hallucinating, and the
        honest reply is 'that is not one of your candidates', not a silent best guess."""
        from libkb.agent.cascade import _fuzzy_path

        key = (name or "").strip()
        return self.by_path.get(key) or _fuzzy_path(key, self.by_path)

    def _tool_find(self, args: dict) -> dict:
        pattern = str(args.get("pattern", ""))
        hits = find_in_candidates(pattern, self.pages)
        return {"result": render_hits(hits, pattern), "matches": len(hits)}

    def _tool_coverage(self, _args: dict) -> dict:
        cov = coverage_map(self.query, self.pages)
        rendered = (
            render_coverage(cov) or "The question has only one part; there is nothing to map."
        )
        return {"result": rendered, "suggested": cov.best_set(self.max_pages)}

    def _tool_read(self, args: dict) -> dict:
        if self.budget.reads >= self.budget.max_reads:
            self.budget.exhausted = self.budget.exhausted or "reads"
            return {"result": "Read budget spent. Choose from what you have already seen."}
        page_id = self._resolve(str(args.get("page", "")))
        if page_id is None:
            return {"result": "That is not one of your candidates. Use a path exactly as listed."}
        self.budget.reads += 1
        try:
            markdown = self.store.page(page_id).markdown
        except NodeNotFound:
            return {"result": "That page is no longer in the library."}
        section = str(args.get("section") or "").strip()
        body = pick_sections(markdown, [section] if section else [], max_tokens=1200)
        return {"result": body[:4000]}

    def _tool_ask(self, args: dict) -> dict:
        if self.budget.lite_calls >= self.budget.max_lite_calls:
            self.budget.exhausted = self.budget.exhausted or "lite_calls"
            return {"result": "No budget left to consult pages. Decide from what you have."}
        page_id = self._resolve(str(args.get("page", "")))
        if page_id is None:
            return {"result": "That is not one of your candidates."}
        self.budget.lite_calls += 1
        try:
            page = self.store.page(page_id)
        except NodeNotFound:
            return {"result": "That page is no longer in the library."}
        question = str(args.get("question") or self.query)
        prompt = self.llm.load_prompt(
            "ask_page",
            question=question,
            path=self.store.path_str(page_id),
            body=f"{page.title}\n\n{page.markdown}"[: self.s.pool_ask_chars],
        )
        try:
            data = self.llm.generate_json(prompt, schema=_ANSWERS_SCHEMA, model=self.s.model_lite)
        except LLMError as exc:
            # One flaky consult costs one consult. The loop is the expensive artifact.
            log.warning("ask_page_failed", error=str(exc)[:120])
            return {"result": "That consult failed; judge the page yourself."}
        verdict = "YES" if data.get("answers") else "NO"
        quote = str(data.get("quote") or "").strip()
        return {"result": f"{verdict} — {quote}" if quote else verdict}

    def _tool_select(self, args: dict) -> dict:
        for row in (args.get("pages") or [])[: self.max_pages]:
            page_id = self._resolve(str(row.get("page", "")))
            if page_id is None or any(s.page_id == page_id for s in self.result.selected):
                continue
            self.result.selected.append(
                Selection(
                    page_id=page_id,
                    sections=[str(x) for x in (row.get("sections") or [])],
                    why=str(row.get("why", "")).strip(),
                )
            )
        self.result.missing = str(args.get("missing") or "").strip()
        return {"result": f"Selected {len(self.result.selected)} page(s)."}

    def _dispatch(self, call: ToolCall) -> ToolResponse:
        table = {
            "find_in_candidates": self._tool_find,
            "coverage_map": self._tool_coverage,
            "read_section": self._tool_read,
            "ask_page": self._tool_ask,
            "select": self._tool_select,
        }
        fn = table.get(call.name)
        payload = (
            fn(call.args or {})
            if fn
            else {"result": f"No tool called {call.name}. Available: {', '.join(table)}."}
        )
        self.result.tool_calls.append(call.name)
        # THE DEADLINE, CARRIED IN THE RESULT (not in a separate turn, which would itself cost a
        # turn). MEASURED: without it, `select` fired voluntarily on 53 of 150 queries and 147 ran
        # out of steps — the loop explored until the budget died. A model cannot pace itself against
        # a ceiling it cannot see. This is not a softening of D-008: the count is still enforced in
        # code and the model is merely told the truth about it.
        if call.name != "select":
            payload = payload | self._deadline()
        return ToolResponse(name=call.name, response=payload, call_id=call.call_id)

    def _deadline(self) -> dict:
        left = max(self.budget.max_steps - self.budget.steps - 1, 0)
        note = {"turns_left": left}
        if left <= 1:
            note["must"] = "This is your last turn. Call `select` now — nothing else counts."
        return note

    # ---------------------------------------------------------------- the loop

    def run(self) -> PoolResult:
        if not self.pages:
            return self.result
        catalogue = "\n".join(f"  {path}" for _, path, _ in self.pages)
        turns: list[Turn] = [
            Turn(
                role="user",
                text=self.llm.load_prompt(
                    "pool_agent",
                    query=self.query,
                    candidates=catalogue,
                    max_pages=self.max_pages,
                ),
            )
        ]

        while True:
            try:
                reply = self.llm.generate(turns, tools=TOOLS)
            except LLMError as exc:
                log.warning("pool_agent_failed", error=str(exc)[:160])
                self.budget.exhausted = self.budget.exhausted or "error"
                break
            if not reply.tool_calls:
                # It answered in prose instead of calling `select`. That is a failure to follow the
                # protocol, not a reason to lose the turn — keep its words as the thought and let
                # the close-out below ask for the basket properly.
                self.result.thought = (reply.text or "").strip()[:300]
                break

            turns.append(Turn(role="model", text=reply.text, tool_calls=reply.tool_calls))
            responses = [self._dispatch(call) for call in reply.tool_calls]
            turns.append(Turn(role="tool", tool_responses=responses))
            if self.result.selected:
                break  # `select` was called — the loop's only successful exit
            if not self.budget.spend_step():
                break

        if not self.result.selected:
            self._close_out(turns)
        log.info(
            "pool_agent_done",
            selected=len(self.result.selected),
            steps=self.budget.steps,
            lite_calls=self.budget.lite_calls,
            reads=self.budget.reads,
            exhausted=self.budget.exhausted or None,
            tools=",".join(self.result.tool_calls),
        )
        if OBSERVER is not None:
            OBSERVER(self.result, self.query)
        return self.result

    def _close_out(self, turns: list[Turn]) -> None:
        """Out of budget, or the model stopped calling tools. Ask ONCE, plainly, for the basket.

        Not a retry of the loop — a single forced `select`. A librarian who has run out of time
        still hands over what he found; going home empty-handed is the one outcome that is strictly
        worse than every alternative (D-035: an empty basket on pages the sieve ranked #1)."""
        turns.append(
            Turn(
                role="user",
                text=(
                    "Stop searching now and call `select` with the best pages you have seen, "
                    "best first. If you are unsure, take them anyway — an empty basket tells the "
                    "reader the library does not hold something it does hold."
                ),
            )
        )
        try:
            reply = self.llm.generate(turns, tools=TOOLS)
        except LLMError as exc:
            log.warning("pool_agent_closeout_failed", error=str(exc)[:120])
            return
        for call in reply.tool_calls or []:
            if call.name == "select":
                self._dispatch(call)
