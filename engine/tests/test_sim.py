import copy

import pytest

from bk.sim.engine import Player, SetSimulator
from bk.sim.library import LIBRARY
from bk.sim.params import SimParams

AVG = {str(i): Player.average(f"P{i}") for i in range(1, 6)}


def sim(set_def, off=AVG, dfn=AVG, seed=1):
    return SetSimulator(set_def, off, dfn, params=SimParams(), seed=seed)


@pytest.mark.parametrize("sid", list(LIBRARY))
def test_library_sets_are_valid_and_plausible(sid):
    r = sim(LIBRARY[sid]).simulate(3000)
    assert 0.7 < r["ppp"] < 1.5
    assert abs(sum(r["points_distribution"].values()) - 1) < 1e-3  # values rounded to 4 dp
    for a in r["actions"].values():
        assert abs(sum(o["prob"] for o in a["options"]) - 1) < 3e-3  # each prob rounded to 3 dp


def test_seed_is_deterministic():
    assert sim(LIBRARY["horns-flare"]).simulate(2000) == sim(LIBRARY["horns-flare"]).simulate(2000)


def test_better_shooter_raises_ppp():
    s = LIBRARY["horns-flare"]
    shooter = Player.average("Shooter")
    shooter.pct = {**shooter.pct, "three_pct": 0.45}
    shooter.ratings = {"three_point": 19}
    off = {**AVG, "2": shooter}
    assert sim(s, off).simulate(8000)["ppp"] > sim(s).simulate(8000)["ppp"]


def test_strong_perimeter_defender_increases_contest():
    s = LIBRARY["horns-flare"]
    stopper = Player.average("Stopper")
    stopper.ratings = {"perimeter_defense": 19}
    base = sim(s).shot_model(s["nodes"]["flare_three"]).p_contest
    tough = sim(s, dfn={**AVG, "2": stopper}).shot_model(s["nodes"]["flare_three"]).p_contest
    assert tough > base


def test_invalid_set_rejected():
    bad = copy.deepcopy(LIBRARY["post-up"])
    bad["nodes"]["post"]["options"][0]["to"] = "nowhere"
    with pytest.raises(ValueError):
        sim(bad)


def test_second_chance_points_count_free_throws_until_the_ball_changes_hands():
    import pandas as pd

    from bk.sim.calibrate import second_chance_points

    rows = [("O", "A"), ("2FGA", "A"), ("D", "B"),          # miss: 0 points on the first rebound
            ("O", "A"), ("FTM", "A"), ("FTA", "A"), ("D", "B"),  # 1 point on the second
            ("O", "A"), ("3FGM", "A"), ("2FGM", "B")]        # 3 on the third; B's basket does not count
    events = pd.DataFrame([{"season": "S", "gamecode": 1, "seq": i, "type": k, "team": tm} for i, (k, tm) in enumerate(rows)])
    assert second_chance_points(events) == (0 + 1 + 3) / 3
