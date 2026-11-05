"""Every formula checked against a small game worked out by hand."""

import numpy as np
import pandas as pd
import pytest

from bk.ratings.metrics_v2 import (INFO_METRICS, SPECS, Spec, Tables, counts, display_value, fit_role, ft_skill, league_level,
                                   role_offset, score_frames, shrink, tier_label)

H = ["h1", "h2", "h3", "h4", "h5"]
A = ["a1", "a2", "a3", "a4", "a5"]
KEY = {"season": "E2099", "gamecode": 1}


def shot(player, value, made, off, dfn, assisted=None, blocked=False, blocker="", heave=False, context="halfcourt",
         group=None):
    group = group or ("inside" if value == 2 else "heave" if heave else "above_break3")
    return {**KEY, "player_id": player, "value": value, "made": made, "off_lineup": off, "def_lineup": dfn,
            "assisted": assisted is not None, "assist_player_id": assisted or "", "blocked": blocked,
            "blocker_id": blocker, "is_heave": heave, "context": context, "lineup_ok": True, "zone_group": group}


def box(player, **stats):
    base = dict.fromkeys(["ftm", "fta", "ast", "tov", "orb", "drb", "stl", "blk", "fg2a", "fg3a"], 0)
    return {**KEY, "player_id": player, "player": player, "team": "H" if player.startswith("h") else "A",
            "minutes": 20.0, **base, **stats}


def game() -> Tables:
    shots = pd.DataFrame([
        shot("h1", 2, True, H, A, assisted="h2"),               # assisted two
        shot("h1", 3, True, H, A),                              # self-made three
        shot("h1", 2, True, H, A, context="putback"),           # putback: no shot creation
        shot("h1", 3, False, H, A, heave=True),                 # heave
        shot("h3", 3, True, H, A, assisted="h2"),               # assisted three
        shot("a1", 2, False, A, H, blocked=True, blocker="h5"),  # blocked two
        shot("a1", 2, True, A, H),
        shot("a2", 3, False, A, H, blocked=True, blocker="h5"),  # blocked three
    ])
    pg = pd.DataFrame([
        box("h1", fg2a=2, fg3a=2, fta=4, ftm=3, tov=2),
        box("h2", ast=3, tov=1, stl=1),                          # 2 assists on shots + 1 on a fouled shot
        box("h3", fg3a=1, orb=1),
        box("h4", drb=2),
        box("h5", blk=2),
        box("a1", fg2a=2),
    ])
    po = pd.DataFrame([{**KEY, "off_lineup": H, "def_lineup": A, "lineup_ok": True}] * 4
                      + [{**KEY, "off_lineup": A, "def_lineup": H, "lineup_ok": True}] * 6
                      + [{**KEY, "off_lineup": H + ["x"], "def_lineup": A, "lineup_ok": False}])

    def rb(off, dfn, player, team_rb=False, dead=False):
        return {**KEY, "off_lineup": off, "def_lineup": dfn, "player_id": player, "team_rebound": team_rb,
                "likely_dead": dead, "lineup_ok": True}

    rebounds = pd.DataFrame([
        rb(H, A, "h3"),                 # h3 offensive rebound
        rb(H, A, "a1"),                 # A's defensive rebound
        rb(H, A, "", team_rb=True),     # team rebound: no player could be credited
        rb(A, H, "h4"), rb(A, H, "h4"),  # h4 defensive rebounds
        rb(A, H, "", team_rb=True, dead=True),  # dead rebound is never a chance
    ])

    def foul(player, kind, drawn=""):
        return {**KEY, "player_id": player, "foul_kind": kind, "drawn_by": drawn}

    fouls = pd.DataFrame([
        foul("h2", "personal", "a1"), foul("h2", "offensive", "a2"), foul("h2", "technical"),
        foul("h2", "bench"),            # not the player's own: never counted
        foul("a1", "personal", "h1"), foul("a2", "personal", "h1"), foul("a3", "unsportsmanlike", "h1"),
        foul("h1", "offensive", "a3"),  # drawn on defense: a3 does not earn offensive foul-drawing credit
    ])
    trips = pd.DataFrame([{**KEY, "player_id": "h1", "kind": k} for k in ["shooting_2", "and_one", "technical", "unsportsmanlike"]])
    return Tables(shots, pg, po, rebounds, fouls, trips, pd.DataFrame())


@pytest.fixture(scope="module")
def c():
    return counts(game())


def rate(c, metric, player):
    return float(c[metric][0].get(player, 0)), float(c[metric][1].get(player, 0))


def test_free_throw(c):
    assert rate(c, "ft_pct", "h1") == (3, 4)


def test_steals_per_defensive_possession_skip_bad_lineups(c):
    assert rate(c, "stl_rate", "h2") == (1, 6)


def test_blocks_count_only_twos_over_opponent_twos_on_court(c):
    assert rate(c, "blk_share", "h5") == (1, 2)  # 2 blocks minus 1 on a three; a1 took 2 twos


def test_foul_rate_doubles_technical_and_ignores_bench(c):
    # personal 1 + offensive 1 + technical 2 over 4 offensive + 6 defensive possessions
    assert rate(c, "foul_rate", "h2") == (4, 10)


def test_rebound_shares_count_only_player_rebounds(c):
    assert rate(c, "orb_share", "h3") == (1, 2)
    assert rate(c, "drb_share", "h4") == (2, 2)


def test_rebound_shares_can_include_live_team_rebounds():
    alt = counts(game(), team_rebounds_count=True)
    assert rate(alt, "orb_share", "h3") == (1, 3)
    assert rate(alt, "drb_share", "h4") == (2, 2)  # the dead team rebound stays out


def test_ball_security_includes_assists_in_the_denominator(c):
    assert rate(c, "tov_share", "h1") == (2, 2 + 2 + 0.44 * 4 + 2)
    assert rate(c, "tov_share", "h2") == (1, 1 + 3)


def test_fouls_drawn_leave_out_offensive_fouls(c):
    assert rate(c, "fd_rate", "h1") == (3, 4)
    assert rate(c, "fd_rate", "a3") == (0, 6)


def test_free_throw_trips_leave_out_technical_and_unsportsmanlike(c):
    assert rate(c, "trip_rate", "h1") == (2, 4)


def test_shot_creation_counts_points_without_putbacks_or_heaves(c):
    assert rate(c, "creation_rate", "h1") == (3, 4)  # only the self-made three


def test_assist_share_uses_teammates_makes_and_fouled_shot_assists(c):
    # h1 made 3 and h3 made 1 while h2 was on court; h2 made none; 1 assist on a fouled shot
    assert rate(c, "ast_share", "h2") == (3, 5)


def test_created_points_weigh_assists_by_shot_value(c):
    assert rate(c, "created_rate", "h2") == (2 + 3 + 1, 4)


def test_shrink_formula_by_hand():
    spec = Spec("prop", k=100)
    s, n = pd.Series({"p": 30.0}), pd.Series({"p": 100.0})
    theta, total, se = shrink(s, n, spec, level=0.4)
    assert theta["p"] == pytest.approx((30 + 100 * 0.4) / 200)
    assert total["p"] == 100
    assert se["p"] == pytest.approx((0.35 * 0.65 / 200) ** 0.5)


def test_shrink_moves_past_counts_to_this_seasons_league_level():
    spec = Spec("prop", k=100)
    s, n = pd.Series({"p": 0.0}), pd.Series({"p": 0.0})
    past = [(pd.Series({"p": 50.0}), pd.Series({"p": 100.0}), 0.40, 0.5)]
    theta, total, _ = shrink(s, n, spec, level=0.30, past=past)
    # past rate 0.50 is 10 points above its league, so 0.40 at today's level, with 50 trials
    assert total["p"] == 50
    assert theta["p"] == pytest.approx((50 * 0.40 + 100 * 0.30) / 150)


def test_shrink_with_role_prior_pulls_toward_the_role():
    spec = Spec("prop", k=100)
    s, n = pd.Series({"big": 0.0, "guard": 0.0}), pd.Series({"big": 0.0, "guard": 0.0})
    theta, _, _ = shrink(s, n, spec, 0.2, offset=pd.Series({"big": 0.1, "guard": -0.1}))
    assert theta["big"] == pytest.approx(0.3) and theta["guard"] == pytest.approx(0.1)


def test_rate_standard_error_uses_dispersion():
    plain, _, se1 = shrink(pd.Series({"p": 10.0}), pd.Series({"p": 100.0}), Spec("rate", 100), 0.1)
    _, _, se2 = shrink(pd.Series({"p": 10.0}), pd.Series({"p": 100.0}), Spec("rate", 100, dispersion=4.0), 0.1)
    assert se2["p"] == pytest.approx(2 * se1["p"])
    assert plain["p"] == pytest.approx(0.1)


def test_shrink_signed_values_toward_the_level():
    theta, total, se = shrink(pd.Series({"p": -30.0}), pd.Series({"p": 100.0}), Spec("resid", 100, dispersion=4.0), 0.0)
    assert theta["p"] == pytest.approx(-0.15)
    assert total["p"] == 100
    assert se["p"] == pytest.approx((4.0 / 200) ** 0.5)


def test_league_level_ignores_players_without_trials():
    assert league_level(pd.Series({"a": 5.0, "b": 99.0}), pd.Series({"a": 10.0, "b": 0.0})) == 0.5


def people_frame():
    rng = np.random.default_rng(0)
    h = rng.integers(180, 220, 200)
    pos = np.where(h > 208, "Center", np.where(h > 196, "Forward", "Guard"))
    return pd.DataFrame({"player_id": [f"p{i}" for i in range(200)], "height": h, "position": pos})


def test_role_fit_finds_taller_players_rebound_more():
    pe = people_frame()
    n = pd.Series(500.0, index=pe.player_id)
    rate_ = 0.05 + 0.003 * (pe.height.to_numpy() - 180)
    s = pd.Series(rate_ * 500, index=pe.player_id)
    beta = fit_role([(s, n, float(rate_.mean()), pe)])
    offset = role_offset(pe.player_id, n, pe, beta)
    tall, short = pe.set_index("player_id").height.idxmax(), pe.set_index("player_id").height.idxmin()
    assert offset[tall] > 0 > offset[short]
    assert abs(offset.mean()) < 1e-9


def test_role_offset_is_zero_for_unknown_players():
    pe = people_frame().assign(height=lambda d: d.height.astype(float))
    pe.loc[0, "height"] = np.nan
    beta = np.array([0.1, 0.002, 0.0, 0.0])
    offset = role_offset(pe.player_id, pd.Series(100.0, index=pe.player_id), pe, beta)
    assert offset["p0"] == 0


def test_three_value_needs_both_attempts_and_accuracy():
    from bk.ratings.metrics_v2 import THREE_BASE_PCT, add_three_value
    m = pd.DataFrame({"three_pct": [0.45, 0.45, 0.33, THREE_BASE_PCT], "games": [10, 10, 10, 10], "n_three_pct": [100.0] * 4, "se_three_pct": [0.02] * 4},
                     index=["few_good", "many_good", "many_plain", "at_base"])
    attempts = pd.Series([20.0, 70.0, 70.0, 70.0], index=m.index)
    out = add_three_value(m, attempts, pd.Series(dtype=float))
    assert out.three_value["many_good"] > out.three_value["few_good"] > out.three_value["many_plain"] > 0
    assert out.three_value["at_base"] == pytest.approx(0)
    # one hot game moves the volume less than the raw average would
    hot = add_three_value(m.assign(games=1), pd.Series(12.0, index=m.index), pd.Series(2.0, index=m.index))
    assert hot.three_attempts_game.iloc[0] < 12


def test_three_point_counts_leave_out_heaves_only(c):
    # h1: one made three, one heave. A three with a bad coordinate would still count (see below).
    assert rate(c, "three_pct", "h1") == (1, 1)
    assert rate(c, "three_rate", "h1") == (1, 4)


def test_three_with_bad_coordinate_stays_a_three():
    g = game()
    extra = shot("h4", 3, True, H, A, group="unknown")
    g.shots = pd.concat([g.shots, pd.DataFrame([extra])], ignore_index=True)
    assert rate(counts(g), "three_pct", "h4") == (1, 1)


def test_mid_and_corner_use_their_clean_zones():
    g = game()
    extra = [shot("h4", 2, True, H, A, group="mid"), shot("h4", 2, False, H, A, group="mid"),
             shot("h4", 3, True, H, A, group="corner3"), shot("h4", 2, False, H, A, group="unknown")]
    g.shots = pd.concat([g.shots, pd.DataFrame(extra)], ignore_index=True)
    c2 = counts(g)
    assert rate(c2, "mid_pct", "h4") == (1, 2)
    assert rate(c2, "mid_rate", "h4") == (2, 4)
    assert rate(c2, "corner3_pct", "h4") == (1, 1)


def test_inside_shots_are_adjusted_for_context():
    shots = pd.DataFrame([
        shot("a", 2, True, H, A, context="putback"), shot("b", 2, False, H, A, context="putback"),
        shot("a", 2, True, H, A), shot("b", 2, True, H, A), shot("b", 2, False, H, A), shot("b", 2, False, H, A),
    ])
    g = game()
    g.shots = shots
    s, n = counts(g)["inside_adj"]
    # league 3/6 = .5; putback .5, halfcourt .5: no adjustment needed, a makes 2 of 2
    assert s["a"] == pytest.approx(2) and n["a"] == 2
    g.shots = pd.concat([shots, pd.DataFrame([shot("b", 2, True, H, A, context="putback"),
                                              shot("b", 2, True, H, A, context="putback")])], ignore_index=True)
    s, n = counts(g)["inside_adj"]
    # league 5/8; putback 3/4, halfcourt 2/4. a: putback make 1-.75+.625 plus halfcourt make 1-.5+.625
    assert s["a"] == pytest.approx(0.875 + 1.125)


def test_inside_volume_counts_attempts_and_self_made_makes_only():
    g = game()
    g.shots = pd.DataFrame([
        shot("h1", 2, True, H, A),                          # self-made: counts for both
        shot("h1", 2, True, H, A, assisted="h2"),           # assisted: attempt only
        shot("h1", 2, True, H, A, context="putback"),       # putback: attempt only
        shot("h1", 2, False, H, A),                         # miss: attempt only
        shot("h1", 2, True, H, A, group="mid"),             # outside the zone: neither
        shot("h1", 3, True, H, A),                          # a three: neither
    ])
    c2 = counts(g)
    assert rate(c2, "inside_rate", "h1") == (4, 4)          # h1 was on court for 4 offensive possessions
    assert rate(c2, "inside_self_rate", "h1") == (1, 4)


def test_usage_counts_touches_per_own_possession(c):
    # h1: 4 shots + 0.44 * 4 free throws + 2 turnovers + 0 assists, over 4 offensive possessions
    assert rate(c, "usage_rate", "h1") == (4 + 0.44 * 4 + 2, 4)
    assert rate(c, "usage_rate", "h2") == (1 + 3, 4)  # one turnover and three assists


def test_low_touch_player_cannot_reach_a_top_ball_security_rating():
    from bk.ratings.method import score_fixed
    from bk.ratings.metrics_v2 import ATTRIBUTES_V2

    security = next(a for a in ATTRIBUTES_V2 if a.key == "ball_security")
    rng = np.random.default_rng(6)
    columns = {"tov_share": rng.normal(0.12, 0.03, 300), "usage_rate": rng.normal(25, 6, 300)}
    extras = {f"{p}_{c}": np.full(300, v) for c in columns for p, v in (("n", 500.0), ("se", 0.01))}
    reference = pd.DataFrame({**columns, **extras, "season": "E2024", "minutes": 1000.0})
    quiet = pd.DataFrame({"tov_share": [0.05], "usage_rate": [12.0], **{f"{p}_{c}": [v] for c in columns for p, v in (("n", 500.0), ("se", 0.01))}})
    busy = quiet.assign(usage_rate=38.0)
    assert score_fixed(quiet, reference, (security,), {})["ball_security"].iloc[0] <= 16
    assert score_fixed(busy, reference, (security,), {})["ball_security"].iloc[0] >= 18


def test_low_volume_cannot_reach_a_top_finishing_rating_on_accuracy_alone():
    """The case that prompted this: 58 of 60 at under two attempts a game must not rate at the top."""
    from bk.ratings.metrics_v2 import ATTRIBUTES_V2
    from bk.ratings.method import score_fixed

    finishing = next(a for a in ATTRIBUTES_V2 if a.key == "finishing")
    rng = np.random.default_rng(5)
    reference = pd.DataFrame({
        "season": "E2024", "minutes": 1000.0,
        "inside_adj": rng.normal(0.6, 0.05, 300), "inside_rate": rng.normal(7, 2.5, 300),
        "inside_self_rate": rng.normal(1.5, 0.7, 300),
        **{f"{c}_{m}": v for m in ("adj", "rate", "self_rate") for c, v in (("n_inside", np.full(300, 500.0)), ("se_inside", np.full(300, 0.01)))},
    })
    columns = {"inside_adj": [0.80], "inside_rate": [3.0], "inside_self_rate": [0.2], "minutes": [500.0]}
    extras = {f"{c}_{m}": [v] for m in ("adj", "rate", "self_rate") for c, v in (("n_inside", 500.0), ("se_inside", 0.01))}
    low_volume = pd.DataFrame({**columns, **extras})
    rating = score_fixed(low_volume, reference, (finishing,), {})["finishing"].iloc[0]
    assert rating <= 16


def test_fit_role_with_free_throw_skill_finds_good_shooters():
    pe = people_frame()
    n = pd.Series(300.0, index=pe.player_id)
    rng = np.random.default_rng(1)
    ft = pd.Series(rng.normal(0, 0.1, len(pe)), index=pe.player_id)
    s = (0.35 + 0.2 * ft) * 300
    beta = fit_role([(s, n, 0.35, pe, ft)])
    assert beta[4] == pytest.approx(0.2, abs=0.01)
    offset = role_offset(pe.player_id, n, pe, beta, ft)
    assert offset[ft.idxmax()] > 0 > offset[ft.idxmin()]


def test_ft_skill_is_relative_to_the_league():
    skill = ft_skill(pd.Series({"good": 90.0, "bad": 50.0}), pd.Series({"good": 100.0, "bad": 100.0}))
    assert skill["good"] > 0 > skill["bad"]


def test_opponent_threes_on_court_leave_out_heaves(c):
    # with h on defense: a2 missed one three; a heave by h1 is on the other side anyway
    assert rate(c, "opp_three_pct", "h1") == (0, 1)
    # with a on defense: h1 made one and h3 made one, the heave does not count
    assert rate(c, "opp_three_pct", "a1") == (2, 2)


def test_tier_labels():
    assert [tier_label(r) for r in (1, 9, 10, 13, 14, 20)] == ["Düşük", "Düşük", "Orta", "Orta", "Yüksek", "Yüksek"]


def test_display_value_uses_number_tier_or_statement():
    assert display_value("three_point", 14) == "14"
    assert display_value("three_point", 14, non_shooter=True) == "Üçlük kullanmıyor"
    assert display_value("mid_range", 15) == "Yüksek"
    assert display_value("mid_range", 15, mid_non_shooter=True) == "Orta mesafe kullanmıyor"
    assert display_value("finishing", 15) == "15"
    assert display_value("perimeter_defense", 15) == "Yüksek"
    assert display_value("team_defense", 15) == "15"
    assert display_value("consistency", 15, games=19) == "Az veri"
    assert display_value("consistency", 15, games=20) == "15"


def test_corner_three_is_information_only():
    from bk.ratings.metrics_v2 import ATTRIBUTES_V2

    assert "corner3_pct" in INFO_METRICS
    used = {m for a in ATTRIBUTES_V2 for m, _, _ in a.components}
    assert "corner3_pct" not in used


def test_every_attribute_has_a_specified_metric():
    from bk.ratings.metrics_v2 import ATTRIBUTES_V2, DERIVED_METRICS

    for a in ATTRIBUTES_V2:
        assert abs(sum(w for _, w, _ in a.components) - 1) < 1e-9, a.key
        for metric, _, _ in a.components:
            assert metric in SPECS or metric in DERIVED_METRICS, metric


def test_score_frames_flags_low_data_by_prior_strength():
    from bk.ratings.attributes import Attribute

    rng = np.random.default_rng(3)
    spec = {"x": Spec("prop", 100)}
    rows = []
    for season, n in (("E2024", 400.0), ("E2025", 400.0), ("E2026", 20.0)):
        for i in range(60):
            rows.append({"season": season, "player_id": f"p{i}", "minutes": 900.0, "x": 0.3 + 0.02 * rng.normal(),
                         "n_x": n, "se_x": 0.01})
    out = score_frames(pd.DataFrame(rows), (Attribute("skill", "S", "hucum", "veri", (("x", 1, 1),)),), spec)
    assert not out[out.season == "E2025"].skill_low_data.any()
    assert out[out.season == "E2026"].skill_low_data.all()
