"""The Librarian role — judges the candidate pages and fills the basket (D-061, Phase B).

A thin wrapper over the existing triage (`cascade._triage` / `_triage_read`): behaviour is the same,
but the cascade RESOLVES this role from the registry instead of a direct call, so the triage
implementation is swappable. It operates on live objects (store, LLM, ranked Hits), so it
exposes a typed `triage()` rather than the generic `run()`."""

from __future__ import annotations

from libkb.agent.roles.base import AgentCard
from libkb.catalog.store import Hit
from libkb.config import Settings
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM


class LibrarianAgent:
    card = AgentCard(
        id="librarian",
        name="Librarian",
        description="Judges the candidates the sieve proposed and fills the basket worth reading "
        "(triage). Reads section headers only, never full bodies.",
        skills=["triage", "select-pages"],
    )

    def triage(
        self,
        query: str,
        batch: list[Hit],
        store: LibraryStore,
        llm: LLM,
        settings: Settings,
        max_pages: int,
    ):
        """Pick the basket. Returns (basket, first-person thought). The triage-MODE branch (D-053)
        lives here now — the one place that decides which selector runs."""
        # Lazy import to avoid a cycle (cascade imports the registry, which imports this role).
        from libkb.agent.cascade import _triage, _triage_read

        if settings.triage_mode == "read":
            return _triage_read(query, batch, store, llm, settings, max_pages)
        return _triage(query, batch, store, llm, settings, max_pages)
