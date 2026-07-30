"""The two FREE set-size selectors — Adaptive-k and conformal filtering.

Everything here is LLM-free and deterministic. The tests that matter most are not the arithmetic
ones; they are the two that guard the ways this measurement could lie:

  - `test_a_query_never_helps_calibrate_its_own_threshold` — the leakage guard. Conformal reads gold
    labels, so an implementation that calibrates on the query it is about to score would report a
    coverage it has not earned. This project has already paid for two metric bugs of that family
    (6.8 basket-size, 6.9 answer cache); a third would be a choice.
  - `test_cross_fitted_conformal_reaches_its_target_coverage` — the guarantee itself, checked on
    synthetic data where the right answer is known.
"""

from __future__ import annotations

import math
import random

import pytest

from libkb.evals.setsize import (
    adaptive_k,
    conformal_keep,
    conformal_quantile,
    cross_fit_thresholds,
    kfold,
    margins,
    required_margin,
)

# --------------------------------------------------------------------------- adaptive-k


def test_adaptive_k_cuts_at_the_sharpest_drop_and_adds_the_buffer():
    # a clean cliff between rank 2 and rank 3
    scores = [0.90, 0.88, 0.87, 0.40, 0.39, 0.38, 0.37, 0.36, 0.35, 0.34]
    assert adaptive_k(scores, buffer=0) == 3
    assert adaptive_k(scores, buffer=5) == 8


def test_the_buffer_is_what_makes_adaptive_k_a_superset_tool():
    """The cliff marks where the RANKING gets vague, not where the evidence ends. A multi-hop
    question's later hops routinely sit just past it — which is the whole reason B exists."""
    scores = [0.90, 0.50, 0.49, 0.48, 0.47]
    assert adaptive_k(scores, buffer=0) == 1, "the drop alone would take one page"
    assert adaptive_k(scores, buffer=3) == 4, "the buffer reaches the pages behind the cliff"


def test_the_tail_of_the_list_cannot_capture_the_cut():
    """Every ranked list falls off a cliff at its very end. Without the search horizon the argmax
    lands there on nearly every query and the selector degenerates to 'take everything'."""
    scores = [0.90, 0.60, 0.58, 0.56, 0.54, 0.52, 0.50, 0.48, 0.46, 0.01]
    assert adaptive_k(scores, buffer=0, search_frac=0.9) == 1
    assert adaptive_k(scores, buffer=0, search_frac=1.0) == 9, "the tail wins once it is in range"


def test_adaptive_k_never_returns_an_empty_basket():
    """D-035: going home empty-handed is the one outcome strictly worse than every alternative."""
    assert adaptive_k([]) == 0
    assert adaptive_k([0.5]) == 1
    assert adaptive_k([0.5] * 8) >= 1, "a flat list has no cliff and must still take something"


def test_ties_resolve_to_the_earlier_cut():
    scores = [0.9, 0.5, 0.4, 0.0]  # two drops of 0.4, at rank 0 and rank 2
    assert adaptive_k(scores, buffer=0, search_frac=1.0) == 1


# --------------------------------------------------------------------------- margins


def test_margins_are_measured_against_the_querys_own_best():
    """Raw cosine is not comparable across queries: an exact match tops out near 0.85 and a vague
    one near 0.55, so one global cutoff would take all of the first and none of the second."""
    want = [0.0, pytest.approx(0.05), pytest.approx(0.25)]
    assert margins([0.85, 0.80, 0.60]) == want
    assert margins([0.55, 0.50, 0.30]) == want, "the same shape must score the same at any scale"


def test_margins_of_an_empty_pool_are_empty():
    assert margins([]) == []


# --------------------------------------------------------------------------- required margin


def test_required_margin_is_set_by_the_WORST_gold_document():
    """The objective is set-valued: the threshold has to reach the deepest true page, not the
    average one. Calibrating on the average is how you certify 90% per document and get 73% per
    query."""
    scores = [0.90, 0.70, 0.50]
    assert required_margin(scores, [0]) == pytest.approx(0.0)
    assert required_margin(scores, [0, 1]) == pytest.approx(0.20)
    assert required_margin(scores, [0, 2]) == pytest.approx(0.40), "the deepest gold sets it"


def test_gold_outside_the_pool_is_not_the_selectors_failure():
    """A sieve miss is the `ceiling`, and no threshold can repair it. Admitting it to the
    calibration would push the quantile out to take the whole pool on every query."""
    assert required_margin([0.9, 0.8], [0, 5]) is None
    assert required_margin([0.9, 0.8], []) is None


# --------------------------------------------------------------------------- the quantile


def test_the_quantile_uses_the_finite_sample_correction():
    # n=9, alpha=0.1 -> ceil(10*0.9) = 9 -> the 9th smallest, i.e. the largest
    vals = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    assert conformal_quantile(vals, 0.10) == pytest.approx(0.9)
    # n=19 -> ceil(20*0.9) = 18 -> the 18th smallest, NOT the 19th: the correction is visible
    vals19 = [i / 20 for i in range(1, 20)]
    assert conformal_quantile(vals19, 0.10) == pytest.approx(18 / 20)


def test_too_few_calibration_points_returns_infinity_not_a_weaker_promise():
    """With n=5 and alpha=0.1, ceil(6*0.9)=6 > 5: the sample cannot certify 90%. Returning the
    largest value on hand would silently deliver a level nobody asked for."""
    assert conformal_quantile([0.1, 0.2, 0.3, 0.4, 0.5], 0.10) == math.inf
    assert conformal_quantile([], 0.10) == math.inf


def test_a_looser_alpha_gives_a_smaller_threshold():
    vals = [i / 100 for i in range(1, 101)]
    assert conformal_quantile(vals, 0.50) < conformal_quantile(vals, 0.10)


# --------------------------------------------------------------------------- keeping


def test_conformal_keep_takes_the_prefix_within_the_threshold():
    scores = [0.90, 0.85, 0.60, 0.20]
    assert conformal_keep(scores, 0.10) == [0, 1]
    assert conformal_keep(scores, 0.30) == [0, 1, 2]


def test_an_infinite_threshold_takes_the_whole_pool():
    assert conformal_keep([0.9, 0.5, 0.1], math.inf) == [0, 1, 2]


def test_conformal_keep_never_returns_nothing():
    """Even a threshold of zero keeps the top-1 — an empty basket is never the honest answer."""
    assert conformal_keep([0.9, 0.5], -1.0) == [0]
    assert conformal_keep([], 0.5) == []


# --------------------------------------------------------------------------- cross-fitting


def test_kfold_is_deterministic_and_balanced():
    a = kfold(103, 5, seed=11)
    assert a == kfold(103, 5, seed=11), "a re-run of the probe must reproduce the thresholds"
    counts = [a.count(f) for f in range(5)]
    assert max(counts) - min(counts) <= 1
    assert len(a) == 103 and set(a) == {0, 1, 2, 3, 4}


def test_kfold_handles_a_sample_smaller_than_the_fold_count():
    assert sorted(kfold(3, 5, seed=1)) == [0, 1, 2]
    assert kfold(0, 5, seed=1) == []


def test_a_query_never_helps_calibrate_its_own_threshold():
    """THE leakage guard.

    One query needs a huge margin and every other needs a tiny one. If that query's threshold were
    calibrated on a set containing itself, the quantile would stretch to cover it and the arm would
    report a superset it did not earn. Cross-fitting must leave it uncovered.
    """
    required = [0.01] * 40 + [9.99]
    thresholds = cross_fit_thresholds(required, alpha=0.10, folds=5, seed=11)
    assert thresholds[-1] < 9.99, "the outlier's own threshold must not have seen the outlier"
    assert thresholds[-1] == pytest.approx(0.01)


def test_cross_fitted_conformal_reaches_its_target_coverage():
    """The guarantee, on data where the answer is known: with exchangeable requirements, the
    fraction of queries whose threshold covers them should land at or above 1-alpha."""
    rng = random.Random(7)
    required = [rng.random() for _ in range(400)]
    for alpha in (0.10, 0.25):
        thresholds = cross_fit_thresholds(required, alpha=alpha, folds=5, seed=11)
        covered = sum(1 for r, t in zip(required, thresholds, strict=True) if r <= t)
        # finite-sample slack: the guarantee is marginal, so allow a few points below nominal
        assert covered / len(required) >= (1 - alpha) - 0.05


def test_every_query_gets_a_threshold_so_n_matches_the_other_arms():
    """Split-conformal would hold out a calibration set and score only the rest, which makes this
    arm incomparable to every other arm in the probe (SELECTION_TARGET rule 2)."""
    required = [0.1, 0.2, None, 0.4, 0.5, 0.6, 0.7, None, 0.9, 1.0]
    thresholds = cross_fit_thresholds(required, alpha=0.5, folds=2, seed=3)
    assert len(thresholds) == len(required)
    assert all(t is not None for t in thresholds)
