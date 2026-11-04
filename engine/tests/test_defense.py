import numpy as np
import pandas as pd
import pytest

from bk.ratings.defense import (DEFENSE_ATTRIBUTES, DEFENSE_K, Design, attach_effect, fit_role_effect, holdout_gain, on_off_card,
                                possession_table, role_prior)
from bk.ratings.metrics_v2 import Tables

PLAYERS = [f"p{i}" for i in range(12)]


def simulated(effects: dict[str, float], possessions=40000, seed=0, base=0.8) -> pd.DataFrame:
    """Random five-man lineups where each defender shifts the opponent's output by a known amount."""
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(possessions):
        lineup = sorted(rng.choice(PLAYERS, 5, replace=False))
        mean = base + sum(effects.get(p, 0.0) for p in lineup)
        rows.append({"def_key": "|".join(lineup), "off_key": "x|y", "inside_points": float(rng.normal(mean, 1.0))})
    return pd.DataFrame(rows)


def test_ridge_recovers_individual_effects_from_lineups():
    truth = {"p0": -0.05, "p1": 0.05}
    out = Design.build(simulated(truth), "inside_points").solve(lam=50)
    assert out.loc["p0", "beta"] < -0.02 and out.loc["p1", "beta"] > 0.02
    assert abs(out.loc["p5", "beta"]) < 0.02


def test_teammates_of_a_good_defender_do_not_inherit_his_effect():
    """The defect in the current metric: everyone on court shares the credit."""
    rows = []
    rng = np.random.default_rng(1)
    star, helper = "star", "helper"
    for _ in range(30000):
        # helper plays mostly next to star, but sometimes without him
        with_star = rng.random() < 0.8
        lineup = ([star] if with_star else ["sub"]) + [helper] + sorted(rng.choice(PLAYERS, 3, replace=False))
        y = 0.8 + (-0.10 if with_star else 0.0) + rng.normal(0, 1.0)
        rows.append({"def_key": "|".join(lineup), "off_key": "x", "inside_points": y})
    out = Design.build(pd.DataFrame(rows), "inside_points").solve(lam=50)
    assert out.loc[star, "beta"] < out.loc[helper, "beta"] - 0.03


def test_prior_decides_when_there_is_little_data():
    d = Design.build(simulated({}, possessions=30), "inside_points")
    prior = pd.Series({p: 0.2 for p in PLAYERS})
    out = d.solve(lam=100000, prior=prior)
    assert out.beta.between(0.15, 0.25).all()


def test_standard_error_falls_with_more_possessions():
    few = Design.build(simulated({}, possessions=500), "inside_points").solve(lam=200)
    many = Design.build(simulated({}, possessions=20000), "inside_points").solve(lam=200)
    assert few.se.mean() > many.se.mean()


def test_offense_players_are_separate_from_defenders():
    rows = pd.DataFrame([{"def_key": "a|b", "off_key": "c|d", "inside_points": 1.0}, {"def_key": "a|b", "off_key": "c|e", "inside_points": 0.0}])
    d = Design.build(rows, "inside_points", use_offense=True)
    assert "D:a" in d.players and "O:c" in d.players
    assert set(d.solve(10).index) == {"a", "b"}


def test_team_effect_is_separated_from_its_players():
    """Everyone on a strong defensive team looks good unless the team itself is modeled."""
    rng = np.random.default_rng(8)
    rows = []
    teams = {"GOOD": [f"g{i}" for i in range(8)], "BAD": [f"b{i}" for i in range(8)]}
    for team, roster in teams.items():
        for _ in range(20000):
            lineup = sorted(rng.choice(roster, 5, replace=False))
            rows.append({"def_key": "|".join(lineup), "off_key": "x", "defense": team,
                         "inside_points": (0.6 if team == "GOOD" else 1.0) + rng.normal(0, 1.0)})
    d = pd.DataFrame(rows)
    plain = Design.build(d, "inside_points").solve(500)
    within = Design.build(d, "inside_points", use_team=True).solve(500)
    gap = lambda o: o.loc[teams["BAD"], "beta"].mean() - o.loc[teams["GOOD"], "beta"].mean()  # noqa: E731
    assert gap(plain) > 0.05
    assert abs(gap(within)) < 0.01


def test_holdout_gain_rewards_real_effects():
    truth = {"p0": -0.1, "p1": 0.1}
    train, test = simulated(truth, seed=2), simulated(truth, seed=3)
    assert holdout_gain(train, test, "inside_points", 50) > 0
    assert holdout_gain(simulated({}, seed=4), simulated({}, seed=5), "inside_points", 100000) == pytest.approx(0, abs=0.1)


def test_possession_table_attributes_output_to_the_right_possession():
    five = ["a", "b", "c", "d", "e"]
    other = ["v", "w", "x", "y", "z"]
    key = {"season": "E2099", "gamecode": 1}
    po = pd.DataFrame([{**key, "poss_no": 0, "points": 3, "def_lineup": five, "off_lineup": other, "lineup_ok": True},
                       {**key, "poss_no": 1, "points": 2, "def_lineup": other, "off_lineup": five, "lineup_ok": True},
                       {**key, "poss_no": 2, "points": 0, "def_lineup": five, "off_lineup": other + ["q"], "lineup_ok": False}])
    shots = pd.DataFrame([
        {**key, "poss_no": 0, "value": 2, "made": False, "zone_group": "inside", "is_heave": False},
        {**key, "poss_no": 0, "value": 3, "made": True, "zone_group": "above_break3", "is_heave": False},
        {**key, "poss_no": 1, "value": 2, "made": True, "zone_group": "inside", "is_heave": False},
        {**key, "poss_no": 1, "value": 3, "made": False, "zone_group": "heave", "is_heave": True},
    ])
    empty = pd.DataFrame()
    d = possession_table(Tables(shots, empty, po, empty, empty, empty, empty)).set_index("poss_no")
    assert len(d) == 2  # the bad-lineup possession is left out
    assert (d.loc[0, "inside_points"], d.loc[0, "inside_fga"], d.loc[0, "three_attempts"], d.loc[0, "points"]) == (0, 1, 1, 3)
    assert (d.loc[1, "inside_points"], d.loc[1, "inside_fga"], d.loc[1, "three_attempts"], d.loc[1, "points"]) == (2, 1, 0, 2)
    assert d.loc[0, "def_key"] == "a|b|c|d|e"


def test_role_prior_is_centered_and_favors_big_shot_blockers():
    index = pd.Index(["big", "guard", "unknown"])
    f = pd.DataFrame({"height": [15.0, -10.0, 0.0], "center": [1.0, 0.0, 0.0], "forward": [0.0, 0.0, 0.0], "blk": [0.03, -0.02, 0.0],
                      "drb": [0.05, -0.05, 0.0], "known": [True, True, False]}, index=index)
    # more height and blocks mean fewer points allowed
    prior = role_prior(f, np.array([0.0, -0.001, 0.0, 0.0, -0.1, 0.0]), pd.Series({"big": 100.0, "guard": 100.0}))
    assert prior["big"] < 0 < prior["guard"]
    assert prior.sum() == pytest.approx(0)
    assert "unknown" not in prior.index


def test_fit_role_effect_finds_the_relation():
    rng = np.random.default_rng(6)
    index = pd.Index([f"p{i}" for i in range(300)])
    f = pd.DataFrame({"height": rng.normal(0, 8, 300), "center": 0.0, "forward": 0.0, "blk": rng.normal(0, 0.02, 300),
                      "drb": rng.normal(0, 0.05, 300), "known": True}, index=index)
    beta = -0.002 * f.height + rng.normal(0, 0.001, 300)
    coefficients = fit_role_effect([beta], [f], [pd.Series(1000.0, index=index)])
    assert coefficients[1] == pytest.approx(-0.002, abs=0.0003)


def test_on_off_card_compares_on_and_off_within_his_games():
    key = {"season": "E2099", "gamecode": 1}
    five = ["a", "b", "c", "d", "e"]
    sub = ["z", "b", "c", "d", "e"]
    other = ["v", "w", "x", "y", "u"]
    po = pd.DataFrame([{**key, "poss_no": 0, "points": 2, "def_lineup": five, "off_lineup": other, "lineup_ok": True, "defense": "H"},
                       {**key, "poss_no": 1, "points": 0, "def_lineup": five, "off_lineup": other, "lineup_ok": True, "defense": "H"},
                       {**key, "poss_no": 2, "points": 2, "def_lineup": sub, "off_lineup": other, "lineup_ok": True, "defense": "H"}])
    shots = pd.DataFrame([
        {**key, "poss_no": 0, "value": 2, "made": True, "zone_group": "inside", "is_heave": False},
        {**key, "poss_no": 1, "value": 2, "made": False, "zone_group": "inside", "is_heave": False},
        {**key, "poss_no": 2, "value": 2, "made": True, "zone_group": "inside", "is_heave": False},
    ])
    empty = pd.DataFrame()
    c = on_off_card(Tables(shots, empty, po, empty, empty, empty, empty)).set_index("player_id")
    assert c.loc["a", "opp_inside_fga_on"] == 100 and c.loc["a", "opp_inside_fga_off"] == 100
    assert c.loc["a", "opp_inside_pct_on"] == 0.5 and c.loc["a", "opp_inside_pct_off"] == 1.0


def test_attach_effect_gives_missing_players_neutral_value_and_wide_uncertainty():
    metrics = pd.DataFrame({"season": ["S", "S"], "player_id": ["a", "b"]})
    effect = pd.DataFrame({"season": ["S"], "player_id": ["a"], "effect": [2.0], "se": [1.5], "n": [100.0]})
    out = attach_effect(metrics, effect, "x").set_index("player_id")
    assert out.loc["b", "x"] == 0 and out.loc["b", "se_x"] == 1.5 and out.loc["b", "n_x"] == 0
    assert out.loc["a", "x"] == 2


def test_defense_attributes_have_prior_strengths():
    for a in DEFENSE_ATTRIBUTES:
        assert abs(sum(w for _, w, _ in a.components) - 1) < 1e-9
    for name in ("rim_effect", "three_att_effect", "team_effect"):
        assert name in DEFENSE_K
