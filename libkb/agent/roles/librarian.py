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
        return selector_for(settings.triage_mode)(query, batch, store, llm, settings, max_pages)


def selector_for(mode: str):
    """The selector callable for a triage mode — the ONE table mapping a mode name to a mechanism.

    Exposed (rather than inlined in `triage`) so the selection probe can run every arm against the
    same cached candidates without round-tripping through Settings for each one; an arm the probe
    reports and a mode production runs are then the same code by construction, not by agreement.
    """
    # Lazy import to avoid a cycle (cascade imports the registry, which imports this role).
    from libkb.agent.cascade import (
        _triage,
        _triage_agent,
        _triage_read,
        _triage_set,
        _triage_trace,
    )

    return {
        "headers": _triage,
        "read": _triage_read,
        "set": _triage_set,
        "trace": _triage_trace,
        "agent": _triage_agent,
    }.get(mode, _triage)
