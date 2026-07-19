"""Feed real questions back into the catalog (ROUTING_REDESIGN §8.4).

A generated question is a guess about what a reader might ask. A logged trajectory is a fact about
what one **did** ask, and about the page that actually answered them. Indexing the second kind is
the only thing in this system that compounds: the head of a Zipf-shaped query distribution can only
be learned from traffic.

Cost: one embed per harvested question (no generation call — the question already exists, written by
a human). That is roughly a tenth of what a generated page costs.

Deliberately conservative:
  - only ANSWERED walks (a not-found teaches the catalog nothing but noise);
  - only walks that landed on exactly ONE page — otherwise we cannot say which page the question is
    really about, and a mislabelled row is worse than a missing one;
  - each trajectory is harvested once (`indexed` flag), so re-running is safe.
"""

from __future__ import annotations

import structlog

from libkb.catalog.store import Catalog
from libkb.library.store import LibraryStore
from libkb.llm.client import LLM, get_llm
from libkb.trajectory.store import TrajectoryStore

log = structlog.get_logger(__name__)


def harvest(
    trajectories: TrajectoryStore,
    catalog: Catalog,
    store: LibraryStore,
    *,
    llm: LLM | None = None,
    limit: int = 100,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    """Index real (question → page) pairs. Returns the pairs it took, as (question, path)."""
    llm = llm or get_llm()
    candidates = trajectories.harvestable(limit=limit)
    if not candidates:
        return []

    taken: list[tuple[str, str]] = []
    used_ids: list[int] = []
    for traj in candidates:
        page_id = traj.page_ids[0]
        try:
            path = store.path_str(page_id)
        except Exception:
            continue  # the page moved or was deleted — a stale trajectory is not a label
        taken.append((traj.query, path))
        used_ids.append(traj.id or 0)

    if dry_run or not taken:
        return taken

    vectors = llm.embed([q for q, _ in taken], task="RETRIEVAL_DOCUMENT")
    for (query, path), vec, traj in zip(taken, vectors, candidates, strict=False):
        page_id = traj.page_ids[0]
        catalog.add_page(
            page_id=page_id,
            book_id=store.get(page_id).parent_id or "",
            path=path,
            texts=[query],
            langs=["real"],  # marks a demand-side row: a question a human actually asked
            embeddings=vec.reshape(1, -1),
        )
    trajectories.mark_indexed(used_ids)
    log.info("trajectories_harvested", n=len(taken))
    return taken
