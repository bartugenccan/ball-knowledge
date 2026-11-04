import numpy as np
import pandas as pd

from bk.ratings.attributes import ATTRIBUTES, score
from bk.ratings.method import (average_priors, center_on_league, estimate_k, fixed_reference, low_data, metric_se,
                               score_fixed)


def metrics_frame(n_players, n_attempts, spread, seed=0):
    """Players with every metric that attributes need, spread around plausible levels."""
    rng = np.random.default_rng(seed)
    components = {c for a in ATTRIBUTES for c, _, _ in a.components}
    data = {}
    for c in components:
        level = 50.0 if c.endswith("_rate") or c == "mpg" else 0.4
        data[c] = level + spread * rng.normal(size=n_players) * (10 if level > 1 else 1)
        data[f"n_{c}"] = np.full(n_players, n_attempts, dtype=float)
    return pd.DataFrame(data).assign(season="E2024", minutes=1000.0)


def test_estimate_k_recovers_true_prior_strength():
    rng = np.random.default_rng(1)
    true_k = 200
    talent = rng.beta(0.36 * true_k, 0.64 * true_k, size=3000)
    n = rng.integers(50, 400, size=3000)
    x = rng.binomial(n, talent) / n
    assert 150 < estimate_k(x, n, 0.36 * 0.64) < 260


def test_estimate_k_is_very_large_without_real_differences():
    rng = np.random.default_rng(2)
    n = np.full(2000, 100)
    x = rng.binomial(n, 0.5) / n
    assert estimate_k(x, n, 0.25) > 1000  # chance alone: 10 times the sample of any player


def test_estimate_k_is_infinite_when_players_differ_less_than_chance():
    assert estimate_k(np.array([0.5, 0.5, 0.5]), np.array([100, 100, 100]), 0.25) == float("inf")


def test_metric_se_shrinks_with_sample():
    m = pd.DataFrame({"three_pct": [0.36, 0.36], "n_three_pct": [10.0, 1000.0]})
    se = metric_se(m, "three_pct")
    assert se[0] > se[1]
    assert abs(se[1] - (0.36 * 0.64 / 1400) ** 0.5) < 1e-9


def test_metric_se_covers_every_rating_component():
    m = metrics_frame(5, 100, 0.01)
    for a in ATTRIBUTES:
        for c, _, _ in a.components:
            assert (metric_se(m, c) > 0).all(), c


def test_fixed_reference_ignores_short_seasons_and_other_seasons():
    m = pd.DataFrame({"season": ["E2024", "E2025", "E2026", "E2024"], "minutes": [600, 500, 900, 499]})
    assert fixed_reference(m).index.tolist() == [0, 1]


def test_small_window_stays_near_the_middle_on_fixed_scale():
    """The core defect: a compressed window ranked against itself still spreads across 1-20."""
    reference = metrics_frame(300, 1000, 0.05, seed=3)
    window = metrics_frame(100, 30, 0.005, seed=4)  # shrunk values: 10 times closer together
    fixed = score_fixed(window, reference)["three_point"]
    old = score(window, window)["three_point"]
    assert old.max() - old.min() >= 12
    assert fixed.max() - fixed.min() <= 6


def test_interval_contains_rating_and_narrows_with_sample():
    reference = metrics_frame(300, 1000, 0.05, seed=5)
    big = score_fixed(metrics_frame(50, 5000, 0.05, seed=6), reference)
    small = score_fixed(metrics_frame(50, 20, 0.05, seed=6), reference)
    for out in (big, small):
        assert (out.three_point_lo <= out.three_point).all() and (out.three_point <= out.three_point_hi).all()
    width = lambda o: (o.three_point_hi - o.three_point_lo).mean()  # noqa: E731
    assert width(small) > width(big)


def test_low_data_means_own_data_carry_under_a_quarter_of_the_estimate():
    m = pd.DataFrame({"a": [0.3, 0.3, 0.3], "n_a": [99.0, 100.0, 500.0], "b": [1.0, 1.0, 1.0], "n_b": [999.0, 999.0, 3.0]})
    assert low_data(m, (("a", 1, 1),), {"a": 300}).tolist() == [True, False, False]
    # any component below the limit flags the attribute
    assert low_data(m, (("a", 0.5, 1), ("b", 0.5, 1)), {"a": 300, "b": 30}).tolist() == [True, False, True]
    # no stable difference between players (infinite k): always low data
    assert low_data(m, (("a", 1, 1),), {"a": float("inf")}).all()
    # a component without a prior strength never flags
    assert not low_data(m, (("a", 1, 1),), {}).any()


def test_score_fixed_uses_supplied_standard_errors():
    reference = metrics_frame(300, 1000, 0.05, seed=11)
    window = metrics_frame(20, 1000, 0.05, seed=12)
    wide = window.assign(se_three_pct=1.0)
    assert (score_fixed(wide, reference).three_point_hi - score_fixed(wide, reference).three_point_lo).mean() > \
        (score_fixed(window, reference).three_point_hi - score_fixed(window, reference).three_point_lo).mean()


def test_lower_is_better_interval_keeps_order():
    out = score_fixed(metrics_frame(50, 50, 0.05, seed=9), metrics_frame(300, 1000, 0.05, seed=10))
    assert (out.ball_security_lo <= out.ball_security).all() and (out.ball_security <= out.ball_security_hi).all()


def test_center_on_league_removes_a_league_level_shift():
    m = pd.DataFrame({"mid_pct": [0.42, 0.45], "player": ["a", "b"], "consistency": [-1.0, -2.0]})
    out = center_on_league(m, {"mid": 0.43}, {"mid": 0.39})
    assert out.mid_pct.round(6).tolist() == [0.38, 0.41]
    assert out.consistency.tolist() == [-1.0, -2.0]  # has no league level, stays as is
    assert m.mid_pct.tolist() == [0.42, 0.45]  # input is not modified


def test_average_priors():
    assert average_priors([{"a": 1.0}, {"a": 3.0}]) == {"a": 2.0}
