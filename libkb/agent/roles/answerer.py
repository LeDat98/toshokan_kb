"""The Answerer role — reads the basket and drafts a cited answer, or an honest NOT_FOUND (Phase B).

A thin wrapper over `answerer.compose_answer`: same behaviour, but resolved from the registry so the
answering implementation is swappable. Operates on live PageContent objects, so it exposes a typed
`compose()` rather than the generic `run()`."""

from __future__ import annotations

from libkb.agent.answerer import Answer
from libkb.agent.roles.base import AgentCard
from libkb.config import Settings
from libkb.library.models import PageContent
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM


class AnswererAgent:
    card = AgentCard(
        id="answerer",
        name="Answerer",
        description="Reads the basket in full and drafts an answer grounded ONLY in it, citing the "
        "pages used — or returns an honest NOT_FOUND when the evidence is insufficient (P6).",
        skills=["compose", "cite", "abstain"],
    )

    def compose(
        self,
        query: str,
        pages: list[PageContent],
        store: LibraryStore,
        *,
        llm: LLM | None = None,
        settings: Settings | None = None,
    ) -> Answer:
        from libkb.agent.answerer import compose_answer

        return compose_answer(query, pages, store, llm=llm, settings=settings)
