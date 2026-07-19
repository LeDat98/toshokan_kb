"""Run independent, network-bound work in parallel (backlog #1).

Ingest and eval spend nearly all their wall-clock WAITING on a provider (an embed or a generate
call), and the GIL is released during that wait — so a thread pool, not processes, is the right
tool: no serialization, one shared LLM client and one shared catalog. The work items must be
genuinely independent (one page, one eval case); the caller owns any shared mutable state.

`parallel_map` keeps the RESULT ORDER of `items` (so a saved eval file lines up with its cases)
while letting them COMPLETE out of order, and reports progress as each finishes. `workers <= 1` is a
plain sequential loop — the old behaviour, and the safe fallback when a provider starts throttling.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")

# A progress callback gets (completed_count, total). Called once per finished item, from the main
# thread in `parallel_map` (as_completed) — so it never needs to be thread-safe itself.
ProgressCB = Callable[[int, int], None]


def parallel_map(
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    workers: int,
    progress: ProgressCB | None = None,
) -> list[R]:
    """Map `fn` over `items` with up to `workers` in flight, preserving input order in the result.

    An exception in `fn` propagates (the caller decides what a failed item means — the eval, for
    instance, catches transport errors INSIDE `fn` and returns a sentinel, so one dropped case never
    kills the batch). `workers <= 1` runs sequentially with no pool at all.
    """
    n = len(items)
    if workers <= 1 or n <= 1:
        out: list[R] = []
        for i, item in enumerate(items, 1):
            out.append(fn(item))
            if progress:
                progress(i, n)
        return out

    results: list[R] = [None] * n  # type: ignore[list-item]  # filled by index, order preserved
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_index = {pool.submit(fn, item): i for i, item in enumerate(items)}
        for done, future in enumerate(as_completed(future_to_index), 1):
            results[future_to_index[future]] = future.result()
            if progress:
                progress(done, n)
    return results
