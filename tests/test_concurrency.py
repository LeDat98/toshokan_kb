"""parallel_map (backlog #1): order-preserving, genuinely concurrent, error-tolerant."""

import time

from libkb.concurrency import parallel_map


def test_preserves_input_order_despite_out_of_order_completion():
    # item 0 sleeps longest, item 4 shortest — if the result followed COMPLETION order it would be
    # reversed. parallel_map must return it in INPUT order regardless.
    def slow(i):
        time.sleep((5 - i) * 0.02)
        return i * 10

    assert parallel_map(slow, [0, 1, 2, 3, 4], workers=5) == [0, 10, 20, 30, 40]


def test_actually_runs_in_parallel():
    # 8 items each sleeping 0.1s: sequential ≈ 0.8s, with 8 workers ≈ 0.1s. Assert well under the
    # sequential floor so the test proves concurrency, not just correctness.
    def sleeper(_):
        time.sleep(0.1)
        return 1

    start = time.monotonic()
    out = parallel_map(sleeper, list(range(8)), workers=8)
    elapsed = time.monotonic() - start
    assert out == [1] * 8
    assert elapsed < 0.4  # 8× headroom over the 0.8s a sequential run would take


def test_workers_one_is_sequential():
    seen = []
    parallel_map(lambda x: seen.append(x), [1, 2, 3], workers=1)
    assert seen == [1, 2, 3]  # in order, no pool


def test_progress_fires_once_per_item():
    ticks = []
    parallel_map(
        lambda x: x,
        [1, 2, 3, 4],
        workers=4,
        progress=lambda done, total: ticks.append((done, total)),
    )
    assert len(ticks) == 4
    assert ticks[-1] == (4, 4)  # last tick reports completion of the whole batch


def test_none_sentinel_passes_through():
    # the eval returns None for a transport-failed case; parallel_map must not choke on it, and the
    # caller counts the Nones as errors.
    out = parallel_map(lambda x: None if x == 2 else x, [1, 2, 3], workers=3)
    assert out == [1, None, 3]
