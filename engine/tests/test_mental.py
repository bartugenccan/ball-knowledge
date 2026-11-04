"""Formulas checked against small games worked out by hand."""

import numpy as np
import pandas as pd
import pytest

from bk.ratings.mental import (clutch_counts, consistency_counts, fit_spread_on_level, game_rating_v2, load_counts,
                               next_game_power, spread_table)
from bk.ratings.metrics_v2 import Tables


def event(seq, kind, player, period=4, clock=100, home=50, away=50, game=1):
    return {"season": "E2099", "gamecode": game, "seq": seq, "period": period, "clock_left": clock, "player_id": player,
            "type": kind, "home_score": home, "away_score": away}


def tables(events=None, pg=None, stints=None):
    empty = pd.DataFrame()
    return Tables(empty, pg if pg is not None else empty, empty, empty, empty, empty, empty,
                  pd.DataFrame(events) if events is not None else None, stints)


def test_clutch_counts_only_close_late_plays_and_includes_turnovers_and_free_throws():
    events = [event(0, "BP", "", period=1, clock=600, home=0, away=0)]
    # 200 ordinary plays by a: 1 point per play
    for i in range(1, 201):
        events.append(event(i, "2FGM" if i % 2 else "2FGA", "a", period=1, clock=500))
    start = len(events)
    events += [event(start, "3FGM", "a"), event(start + 1, "TO", "a"), event(start + 2, "FTM", "a"), event(start + 3, "FTA", "a")]
    # not clutch: 20-point game, and too early in the fourth
    events += [event(start + 4, "BP", "", clock=100, home=80, away=60), event(start + 5, "3FGM", "a", clock=100, home=80, away=60),
               event(start + 6, "BP", "", clock=400), event(start + 7, "3FGM", "a", clock=400)]
    c = clutch_counts(tables(events))
    points, use = c["clutch_points"]
    assert points["a"] == 4  # 3 + 0 + 1 + 0
    assert use["a"] == pytest.approx(1 + 1 + 0.44 + 0.44)
    value, n = c["clutch_value"]
    assert n["a"] == pytest.approx(use["a"])
    # expected = own usual efficiency * use. Usual plays include the two late threes outside the clutch window.
    usual_points, usual_use = 100 * 2 + 3 + 3, 200 + 2
    league = (usual_points + 4) / (usual_use + use["a"])
    own = (usual_points + 100 * league) / (usual_use + 100)
    assert value["a"] == pytest.approx(4 - own * use["a"])


def test_clutch_margin_is_taken_before_the_play():
    events = [event(0, "BP", "", home=50, away=44), event(1, "2FGM", "a", home=52, away=44)]  # 6 before, not clutch
    events += [event(2, "BP", "", home=50, away=45), event(3, "2FGM", "b", home=52, away=45)]  # 5 before, clutch
    _, use = clutch_counts(tables(events))["clutch_points"]
    assert "a" not in use.index and use["b"] == 1


def test_load_counts_minutes_per_team_game_and_long_stint_share():
    pg = pd.DataFrame([{"player_id": "a", "team": "H", "gamecode": g, "minutes": 30.0} for g in (1, 2)]
                      + [{"player_id": "b", "team": "H", "gamecode": g, "minutes": 10.0} for g in (1, 2, 3)])
    stints = pd.DataFrame([{"player_id": "a", "seconds": 600.0}, {"player_id": "a", "seconds": 300.0},
                           {"player_id": "b", "seconds": 419.0}])
    c = load_counts(tables(pg=pg, stints=stints))
    minutes, games = c["load_minutes"]
    assert (minutes["a"], games["a"]) == (60, 3)  # missed one of the team's three games
    assert (minutes["b"], games["b"]) == (30, 3)
    long_minutes, all_minutes = c["long_stint_share"]
    assert long_minutes["a"] == 10 and all_minutes["a"] == 15
    assert long_minutes.get("b", 0) == 0  # 419 seconds is not a long stint


def box_line(player, game, minutes, pts):
    return {"season": "E2099", "player_id": player, "gamecode": game, "minutes": minutes, "pts": pts, "fg2m": 0, "fg2a": 0, "fg3m": 0,
            "fg3a": 0, "fta": 0, "ftm": 0, "orb": 0, "drb": 0, "stl": 0, "ast": 0, "blk": 0, "pf": 0, "tov": 0, "plus_minus": 0,
            "date": pd.Timestamp("2099-01-01") + pd.Timedelta(days=game)}


def test_spread_table_measures_swing_around_own_level_and_skips_short_games():
    steady = [box_line("s", g, 20, 10) for g in range(1, 11)]
    swing = [box_line("w", g, 20, 20 if g % 2 else 0) for g in range(1, 11)]
    cameo = [box_line("s", 11, 2, 40)]
    d = spread_table(pd.DataFrame(steady + swing + cameo))
    assert d.loc["s", "spread"] == 0 and d.loc["s", "n"] == 10  # the 2-minute game is ignored
    assert d.loc["w", "spread"] > 10
    assert d.loc["s", "level"] == pytest.approx(15)  # 200 points over 200 minutes, per 30


def test_consistency_compares_players_at_the_same_level():
    rows = []
    for i in range(60):
        level = 10 + i
        for g in range(1, 21):
            noise = (1 if g % 2 else -1) * level * 0.5
            rows.append(box_line(f"p{i}", g, 30, level + noise))
    pg = pd.DataFrame(rows)
    d = spread_table(pg)
    coefficients = fit_spread_on_level([d])
    assert coefficients[1] > 0  # more output, more swing
    excess, n = consistency_counts(pg, coefficients)
    assert (excess / n).abs().max() < 0.5  # same relative swing: nobody stands out
    assert n["p0"] == 20


def test_short_samples_do_not_look_steadier_than_full_seasons():
    """Few games understate the spread; the fit must remove that, or everyone looks steady early on."""
    rng = np.random.default_rng(4)
    rows = []
    for p in range(150):
        games = 6 if p < 75 else 40
        for g in range(1, games + 1):
            rows.append(box_line(f"p{p}", g, 30, 12 + rng.normal(0, 5)))
    pg = pd.DataFrame(rows)
    coefficients = fit_spread_on_level([spread_table(pg)])
    excess, n = consistency_counts(pg, coefficients)
    value = excess / n
    short = [f"p{i}" for i in range(75)]
    full = [f"p{i}" for i in range(75, 150)]
    assert abs(value[short].mean() - value[full].mean()) < 0.3


def test_game_rating_rewards_above_usual_production_for_the_minutes():
    g = game_rating_v2(pd.DataFrame([box_line("a", i, 30, 30 if i == 1 else 10) for i in range(1, 21)]))
    best = g.sort_values("game_rating").iloc[-1]
    assert best.gamecode == 1 and best.game_rating > 6.6
    assert not g.short_game.any()


def test_short_games_are_marked_and_rating_stays_in_range():
    rows = [box_line("a", i, 30, 10) for i in range(1, 20)] + [box_line("a", 20, 4, 0), box_line("a", 21, 40, 200)]
    g = game_rating_v2(pd.DataFrame(rows))
    assert g.short_game.sum() == 1
    assert g.game_rating.between(3, 10).all()


def test_plus_minus_weight_changes_the_rating():
    rows = [box_line("a", i, 30, 10 + i % 3) for i in range(1, 21)]
    for i, r in enumerate(rows):
        r["plus_minus"] = 20 if i == 0 else 0
    frame = pd.DataFrame(rows)
    assert game_rating_v2(frame, 0.1).game_z.iloc[0] > game_rating_v2(frame).game_z.iloc[0]


def test_next_game_power_finds_a_player_who_stays_hot():
    rng = np.random.default_rng(0)
    rows = []
    for p in range(50):
        level = 0.0
        for g in range(1, 31):
            level = 0.9 * level + rng.normal(0, 4)
            rows.append(box_line(f"p{p}", g, 30, 12 + level))
    assert next_game_power(game_rating_v2(pd.DataFrame(rows))) > 0.3
