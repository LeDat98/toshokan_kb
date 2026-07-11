"""Entry point: dispatch a query to a walk, then compose the answer.

P1 is minimal — every query is an exploratory walk from the root. The front-door
query classifier and the lookup/synthesis strategies arrive in P3 (see docs/ARCHITECTURE.md).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from libkb.agent.answerer import Answer, compose_answer, compose_not_found
from libkb.agent.navigator import NavResult, navigate
from libkb.agent.tools import NavEvent
from libkb.config import get_settings
from libkb.exceptions import LLMError
from libkb.library.store import LibraryStore

EventCB = Callable[[NavEvent], None]


@dataclass
class QueryResult:
    answer: Answer
    nav: NavResult


def answer_query(
    query: str,
    *,
    store: LibraryStore | None = None,
    event_cb: EventCB | None = None,
) -> QueryResult:
    store = store or LibraryStore(get_settings().library_dir)
    nav = navigate(query, store=store, event_cb=event_cb)

    if nav.status == "FOUND" and nav.pages:
        answer = compose_answer(query, nav.pages, store)
    else:
        answer = compose_not_found(query, nav.closest)
    return QueryResult(answer=answer, nav=nav)


def answer_query_safe(
    query: str,
    *,
    store: LibraryStore | None = None,
    event_cb: EventCB | None = None,
) -> QueryResult:
    """Same as answer_query but converts LLM failures into an honest not-found."""
    try:
        return answer_query(query, store=store, event_cb=event_cb)
    except LLMError as exc:
        note = f"(The librarian couldn't reach the model: {exc})"
        return QueryResult(
            answer=compose_not_found(query, [], note=note),
            nav=NavResult(status="NOT_FOUND", reason=str(exc)),
        )
