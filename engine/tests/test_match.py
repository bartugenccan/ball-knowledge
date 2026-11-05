import json

import pandas as pd
import pytest

from bk.config import TABLES_DIR
from bk.match.calibrate import CALIBRATION_FILE, MINUTES
from bk.match.model import PlayerModel, TeamModel
from bk.match.narrate import full_name, key_moments, line, quarter_summaries, scoring_runs, short_name
from bk.match.runner import flow_from_scores, run_many, running_score
from bk.match.sim import FOUL_OUT, GameSim, PF, SEC, Tuning

pytestmark = pytest.mark.skipif(not CALIBRATION_FILE.exists(), reason="calibration not built (run bk.match.calibrate)")


@pytest.fixture(scope="module")
def league():
    return json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))


def player(i: int, starter: bool, target: float, position: str, make: float = 0.0, three: float = 7.0) -> PlayerModel:
    return PlayerModel(
        player_id=f"P{i}", name=f"PLAYER{i}, TEST", position=position, starter=starter, ft=0.78,
        make={"inside": make + 0.25, "mid": make - 0.45, "corner3": make - 0.3, "above_break3": make - 0.6},
        rate={"inside": 9.0, "mid": 2.0, "three": three}, corner_share=0.13, self_share=0.0, tov=3.2, trip=3.0, fd=6.0, foul=6.0, stl=1.6,
        blk=0.014, orb=0.055, drb=0.145, ast=0.12, rim_effect=0.0, three_effect=0.0, target=target,
        curve=[min(0.95, target / 40)] * MINUTES, stint=5.0)


def team(code: str, make: float = 0.0, base: int = 0) -> TeamModel:
    positions = ["Guard", "Guard", "Forward", "Forward", "Center", "Guard", "Guard", "Forward", "Forward", "Center", "Guard", "Forward"]
    minutes = [30, 28, 28, 26, 24, 16, 14, 12, 10, 8, 3, 1]
    return TeamModel(code, code, [player(base + i, i < 5, minutes[i], positions[i], make) for i in range(12)])


def play(league, seed=1, tune=None, trace=False, home=None, away=None):
    return GameSim(home or team("HOM"), away or team("AWY", base=100), league, tune, seed=seed, trace=trace).play()


def test_same_seed_same_game_with_or_without_events(league):
    a = play(league, seed=9)
    b = play(league, seed=9, trace=True)
    assert (a.sides[0].pts, a.sides[1].pts, a.quarters) == (b.sides[0].pts, b.sides[1].pts, b.quarters)
    assert a.sides[0].box == b.sides[0].box


def test_box_score_adds_up_to_the_score(league):
    g = play(league, seed=3)
    for s in g.sides:
        rows = s.box
        total = sum(2 * r[2] + 3 * r[4] + r[6] for r in rows)
        assert total == s.pts
        assert sum(r[1] for r in rows) == s.pts


def test_every_second_has_five_players_on_court(league):
    for seed in range(5):
        g = play(league, seed=seed)
        seconds = 4 * 600 + (len(g.quarters) - 4) * 300
        for s in g.sides:
            assert sum(r[SEC] for r in s.box) == pytest.approx(5 * seconds, abs=1.0)


def test_no_one_plays_on_past_five_fouls_unless_the_bench_is_empty(league):
    for seed in range(20):
        g = play(league, seed=seed, trace=True)
        fouls = {}
        for e in g.events:
            if e["event"] == "foul":
                fouls[e["player_id"]] = e["fouls"]
        assert all(v <= FOUL_OUT + 1 for v in fouls.values())
        for s in g.sides:
            assert all(r[PF] <= FOUL_OUT + 1 for r in s.box)


def test_games_are_never_tied_at_the_end(league):
    for seed in range(30):
        g = play(league, seed=seed)
        assert g.sides[0].pts != g.sides[1].pts


def test_better_shooting_wins_more(league):
    even = run_many(team("HOM"), team("AWY", base=100), league, n=150, seed=1)
    strong = run_many(team("HOM", make=0.35), team("AWY", base=100), league, n=150, seed=1)
    assert strong.home_win > even.home_win + 0.15


def test_home_side_has_an_edge_when_teams_are_equal(league):
    home = run_many(team("HOM"), team("AWY", base=100), league, n=300, seed=5)
    neutral = run_many(team("HOM"), team("AWY", base=100), league, n=300, seed=5, neutral=True)
    assert (home.home_pts - home.away_pts).mean() > (neutral.home_pts - neutral.away_pts).mean()


def test_league_average_teams_look_like_a_real_game(league):
    m = run_many(team("HOM"), team("AWY", base=100), league, n=120, seed=2)
    for side in (0, 1):
        assert 60 < m.team[side]["poss"].mean() < 90
        assert 65 < m.team[side]["pts"].mean() < 105
        assert 40 < m.team[side]["fga"].mean() < 85
    assert 15 < m.subs.mean() < 50


def test_score_effect_narrows_the_spread(league):
    plain = run_many(team("HOM"), team("AWY", base=100), league, Tuning(score_effect=0.0), n=250, seed=4)
    pulled = run_many(team("HOM"), team("AWY", base=100), league, Tuning(score_effect=-0.02), n=250, seed=4)
    assert (pulled.home_pts - pulled.away_pts).std() < (plain.home_pts - plain.away_pts).std()


def test_flow_counts_lead_changes_ties_and_runs():
    rows = [(10.0, 2, 0), (20.0, 4, 0), (30.0, 4, 3), (40.0, 4, 5), (50.0, 7, 5), (60.0, 7, 7)]
    f = flow_from_scores(rows)
    assert f["lead_changes"] == 2      # home, away, home
    assert f["ties"] == 1
    assert f["max_lead_home"] == 4
    assert f["max_lead_away"] == 1
    assert f["best_run_home"] == 4
    assert f["best_run_away"] == 5


def test_running_score_comes_from_the_baskets():
    rows = pd.DataFrame({"elapsed": [10, 20, 30, 700], "type": ["2FGM", "3FGM", "2FGM", "FTM"], "team": ["HOM", "HOM", "AWY", "AWY"], "period": [1, 1, 1, 2]})
    score, quarters = running_score(rows, "HOM")
    assert [s[1:] for s in score] == [(2, 0), (5, 0), (5, 2), (5, 3)]
    assert quarters == [[5, 2], [5, 3], [5, 3], [5, 3]]
    assert flow_from_scores(score)["best_run_home"] == 5


def test_name_formats():
    assert full_name("HEZONJA, MARIO") == "Mario Hezonja"
    assert short_name("CLARK III, GARY") == "Clark III"
    assert short_name("MILLER-MCINTYRE, CODI") == "Miller-McIntyre"
    assert short_name("M'BAYE, AMATH") == "M'Baye"


def test_lines_say_only_what_the_data_knows():
    forbidden = ("perde", "pick", "izole", "drive", "savundu", "boş", "kontes")
    event = {"event": "make", "player": "HEZONJA, MARIO", "player_id": "P1", "zone": "corner3", "context": "transition", "assist": "CAMPAZZO, FACUNDO"}
    text, _ = line(event, {})
    assert "Hezonja" in text and "Campazzo" in text and "köşeden üçlük" in text
    assert not any(w in text.lower() for w in forbidden)


def test_rating_note_respects_low_data_and_tiers():
    ratings = {"P1": {"values": {"three_point": 18, "mid_range": 17}, "labels": {"mid_range": "Yüksek"}, "low_data": []},
               "P2": {"values": {"three_point": 18}, "labels": {}, "low_data": ["three_point"]}}
    made = {"event": "make", "player": "A, B", "zone": "above_break3", "context": "halfcourt", "assist": None}
    assert line({**made, "player_id": "P1"}, ratings)[1] == "Üçlük 18"
    assert line({**made, "player_id": "P2"}, ratings)[1] is None
    assert line({**made, "player_id": "P1", "zone": "mid"}, ratings)[1] == "Orta Mesafe Yüksek"


def test_runs_and_moments_come_from_the_events():
    def ev(period, clock, elapsed, h, a, team="HOM", kind="make", player="A, B"):
        return {"event": kind, "period": period, "clock": clock, "elapsed": elapsed, "home": h, "away": a, "team": team, "player": player}
    events = [ev(1, "9:00", 60, 0, 2, "AWY"), ev(1, "8:00", 120, 3, 2), ev(1, "7:00", 180, 6, 2), ev(1, "6:00", 240, 9, 2), ev(1, "5:00", 300, 9, 4, "AWY")]
    assert scoring_runs(events)[0]["points"] == 9
    assert any("9-0" in m["text"] for m in key_moments(events, "HOM", "AWY"))


def test_a_period_run_counts_from_the_score_it_started_at():
    def ev(period, elapsed, h, a, team):
        return {"event": "make", "period": period, "clock": "5:00", "elapsed": elapsed, "home": h, "away": a, "team": team, "player": "A, B", "value": 2}
    events = [ev(1, 100, 50, 41, "HOM"), ev(2, 700, 50, 43, "AWY"), ev(2, 800, 52, 43, "HOM")]
    assert scoring_runs(events[1:], 2, (50, 41))[0]["points"] == 2
    summaries = quarter_summaries(events, "HOM", "AWY")
    assert all(r["points"] < 20 for s in summaries[1:] for r in s["runs"])


@pytest.mark.skipif(not (TABLES_DIR / "ratings_season.parquet").exists(), reason="tables not built")
def test_real_play_by_play_adds_up_to_the_final_score():
    from bk.match.report import real_events
    from bk.match.runner import games_table
    from bk.ratings.metrics_v2 import load_tables
    t = load_tables()
    g = games_table()
    for r in g[g.season == "E2026"].head(12).itertuples():
        events = real_events(t, "E2026", r.gamecode, r.home, r.away)
        assert (events[-1]["home"], events[-1]["away"]) == (r.home_score, r.away_score)


@pytest.mark.skipif(not (TABLES_DIR / "ratings_season.parquet").exists(), reason="tables not built")
def test_snapshot_never_sees_the_game_it_simulates():
    from bk.match.asof import before
    from bk.ratings.metrics_v2 import load_tables
    t = load_tables()
    g = t.player_games[t.player_games.season == "E2026"].sort_values("date")
    cutoff = g.date.iloc[len(g) // 2]
    cut = before(t, "E2026", cutoff)
    later = g[g.date >= cutoff].gamecode.unique()
    assert not cut.shots[(cut.shots.season == "E2026") & cut.shots.gamecode.isin(later)].shape[0]
    assert not cut.events[(cut.events.season == "E2026") & cut.events.gamecode.isin(later)].shape[0]
    assert not cut.stints[(cut.stints.season == "E2026") & cut.stints.gamecode.isin(later)].shape[0]
    assert cut.player_games[cut.player_games.season == "E2025"].shape[0] > 0
