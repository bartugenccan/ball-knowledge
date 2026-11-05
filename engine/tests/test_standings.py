import pandas as pd

from bk.team.standings import standings


def games(rows):
    return pd.DataFrame([{"season": "E2099", "phase": row[4] if len(row) > 4 else "RS", "gamecode": i, "date": pd.Timestamp("2099-10-01", tz="UTC") + pd.Timedelta(days=i),
                          "home": row[0], "away": row[1], "home_name": row[0], "away_name": row[1], "home_score": row[2], "away_score": row[3]} for i, row in enumerate(rows)])


def test_wins_decide_first_and_the_record_adds_up():
    t = standings(games([("AAA", "BBB", 90, 80), ("BBB", "CCC", 70, 60), ("AAA", "CCC", 80, 70)]), "E2099")
    assert [r["code"] for r in t] == ["AAA", "BBB", "CCC"]
    assert (t[0]["wins"], t[0]["losses"], t[0]["diff"], t[0]["home"], t[0]["away"]) == (2, 0, 20, "2-0", "0-0")
    assert (t[1]["home"], t[1]["away"], t[1]["last5"]) == ("1-0", "0-1", [False, True])


def test_head_to_head_counts_only_after_both_games():
    # AAA has the far better overall difference, and BBB won the only meeting so far
    one_game = [("BBB", "AAA", 71, 70), ("AAA", "CCC", 120, 60), ("DDD", "BBB", 80, 60)]
    assert [r["code"] for r in standings(games(one_game), "E2099") if r["code"] in ("AAA", "BBB")] == ["AAA", "BBB"]
    # both legs played, wins level: the points between them decide, not the far better overall difference
    both = [("BBB", "AAA", 90, 70), ("AAA", "BBB", 80, 70), ("AAA", "CCC", 120, 60), ("BBB", "CCC", 90, 70)]
    t = standings(games(both), "E2099")
    assert [r["code"] for r in t if r["code"] in ("AAA", "BBB")] == ["BBB", "AAA"]


def test_points_difference_leaves_out_overtime():
    rows = [("AAA", "BBB", 100, 90)]
    regulation = pd.DataFrame({"season": ["E2099"], "gamecode": [0], "reg_home": [85], "reg_away": [85]})
    t = {r["code"]: r for r in standings(games(rows), "E2099", regulation)}
    assert t["AAA"]["diff"] == 0 and t["AAA"]["scored"] == 100 and t["AAA"]["wins"] == 1


def test_split_meetings_go_to_points_difference_between_the_two():
    rows = [("AAA", "BBB", 90, 80), ("BBB", "AAA", 90, 85)]
    t = standings(games(rows), "E2099")
    assert t[0]["code"] == "AAA"    # +10 and -5 against -10 and +5


def test_play_offs_and_unplayed_games_do_not_count():
    rows = [("AAA", "BBB", 90, 80), ("BBB", "AAA", 90, 80, "PO"), ("BBB", "AAA", None, None)]
    t = {r["code"]: r for r in standings(games(rows), "E2099")}
    assert t["AAA"]["games"] == 1 and t["BBB"]["games"] == 1


def test_streak_and_zones():
    rows = [("AAA", "BBB", 90, 80), ("AAA", "BBB", 90, 80), ("BBB", "AAA", 90, 80)]
    t = {r["code"]: r for r in standings(games(rows), "E2099")}
    assert t["AAA"]["streak"] == "M1" and t["BBB"]["streak"] == "G1"
    assert t["AAA"]["zone"] == "playoff"
