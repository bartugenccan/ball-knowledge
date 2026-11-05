import pandas as pd

from bk.match.baselines import NetRatings, fit_logistic, player_averages


def games():
    return pd.DataFrame({"season": ["E2099"] * 2, "gamecode": [1, 2], "date": pd.to_datetime(["2099-10-01", "2099-10-08"], utc=True),
                         "home": ["AAA", "AAA"], "away": ["BBB", "BBB"], "home_score": [90, 70], "away_score": [70, 90]})


def poss():
    rows = []
    for code, a, b in ((1, 2, 0), (2, 0, 2)):
        rows += [{"season": "E2099", "gamecode": code, "offense": "AAA", "defense": "BBB", "points": a}] * 50
        rows += [{"season": "E2099", "gamecode": code, "offense": "BBB", "defense": "AAA", "points": b}] * 50
    return pd.DataFrame(rows)


def test_net_rating_only_sees_earlier_games():
    nets = NetRatings(poss(), games())
    before_first = nets.before("E2099", pd.Timestamp("2099-10-01", tz="UTC"))
    assert before_first == {} or all(v == 0 for v in before_first.values())
    after_first = nets.before("E2099", pd.Timestamp("2099-10-08", tz="UTC"))
    assert after_first["AAA"] > 0 > after_first["BBB"]    # game two, which AAA lost badly, is not counted


def test_player_averages_exclude_the_game_itself():
    pg = pd.DataFrame({"season": ["E2099"] * 3, "gamecode": [1, 2, 3], "date": pd.to_datetime(["2099-10-01", "2099-10-08", "2099-10-15"], utc=True),
                       "player_id": ["P1"] * 3, "minutes": [20.0, 0.0, 30.0], "pts": [10, 0, 40]})
    out = player_averages(pg, {"pts": "pts"}).set_index("gamecode")
    assert pd.isna(out.loc[1, "pts_avg"])
    assert out.loc[2, "pts_avg"] == 10        # sees game one only
    assert out.loc[3, "pts_avg"] == 10        # a game he did not play does not count as zero


def test_logistic_finds_the_home_edge_and_the_slope():
    import numpy as np
    x = np.linspace(-20, 20, 400)
    y = (np.sin(np.arange(400) * 12.9898) * 43758.5453 % 1 < 1 / (1 + np.exp(-(0.5 + 0.1 * x)))).astype(float)
    home, slope = fit_logistic(x, y)
    assert 0.1 < home < 0.9 and 0.05 < slope < 0.16
