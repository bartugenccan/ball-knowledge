import pandas as pd

from bk.model.clean import (flag_possessions, flag_rebounds, flag_shots, fouls_table, ft_trips, link_blocks,
                            parse_official, parse_people)


def events(rows):
    """rows: (type, team, player, clock). Feed order becomes seq."""
    return pd.DataFrame([{"season": "E2099", "gamecode": 1, "seq": i, "period": period, "clock_left": clock,
                          "team": team, "player_id": player, "type": kind}
                         for i, (kind, team, player, clock, period) in
                         enumerate((*r, 1) if len(r) == 4 else r for r in rows)])


def shot(value, x, y, made=False, seq=0, player="A1", clock=300):
    dist = (x**2 + y**2) ** 0.5 / 100
    return {"season": "E2099", "gamecode": 1, "seq": seq, "period": 1, "clock_left": clock, "team": "HOM",
            "player_id": player, "value": value, "made": made, "x": x, "y": y, "dist_m": dist,
            "zone": "above_break3" if value == 3 else "rim", "def_lineup": ["a", "b", "c", "d", "e"]}


def test_flag_shots_marks_each_problem_without_touching_zone():
    s = flag_shots(pd.DataFrame([
        shot(3, 0, 750),      # normal three
        shot(3, 0, 1500),     # heave
        shot(2, 0, 0),        # no real coordinate
        shot(3, 0, 300),      # a three from 3 m
        shot(2, 0, 800),      # a two from 8 m
        shot(3, 660, 50),     # legal corner three at 6.62 m
    ]))
    assert s.is_heave.tolist() == [False, True, False, False, False, False]
    assert s.coord_valid.tolist() == [True, True, False, True, True, True]
    assert s.value_dist_ok.tolist() == [True, True, True, False, False, True]
    assert s.zone_clean.tolist() == ["above_break3", "heave", "unknown", "unknown", "unknown", "above_break3"]
    assert s.zone.tolist() == ["above_break3", "above_break3", "rim", "above_break3", "rim", "above_break3"]


def test_zone_group_merges_rim_and_paint_only():
    s = pd.DataFrame([shot(2, 0, 50), shot(2, 100, 300), shot(2, 400, 300), shot(3, 660, 50), shot(3, 0, 750)])
    s["zone"] = ["rim", "paint", "mid", "corner3", "above_break3"]
    assert flag_shots(s).zone_group.tolist() == ["inside", "inside", "mid", "corner3", "above_break3"]



def test_flag_shots_marks_bad_lineup():
    bad = {**shot(3, 0, 750), "def_lineup": ["a", "b", "c", "d"]}
    assert flag_shots(pd.DataFrame([shot(3, 0, 750), bad])).lineup_ok.tolist() == [True, False]


def test_flag_possessions():
    five = list("abcde")
    p = flag_possessions(pd.DataFrame([
        {"off_lineup": five, "def_lineup": five, "start": 0, "end": 10},
        {"off_lineup": five + ["f"], "def_lineup": five, "start": 10, "end": 20},
        {"off_lineup": five, "def_lineup": five, "start": 30, "end": 20},
    ]))
    assert p.lineup_ok.tolist() == [True, False, True]
    assert p.time_ok.tolist() == [True, True, False]


def test_fouls_count_per_period_and_overtime_continues_fourth():
    ev = events([("CM", "AWY", "a", 500, 4), ("C", "AWY", "coach", 400, 4), ("CM", "AWY", "b", 100, 4),
                 ("CM", "AWY", "c", 200, 5), ("CM", "AWY", "d", 500, 1)])
    f = fouls_table(ev).set_index("player_id")
    assert f.loc["a", "team_fouls"] == 1
    assert f.loc["coach", "foul_kind"] == "coach" and f.loc["coach", "team_fouls"] == 1  # coach foul does not count
    assert f.loc["b", "team_fouls"] == 2
    assert f.loc["c", "team_fouls"] == 3  # overtime keeps counting
    assert f.loc["d", "team_fouls"] == 1  # a different period starts over


def test_foul_drawn_is_matched_by_time_not_adjacency():
    ev = events([("RV", "AWY", "defender", 100), ("D", "AWY", "x", 100), ("OF", "HOM", "attacker", 100),
                 ("TO", "HOM", "attacker", 100)])
    f = fouls_table(ev)
    assert f.foul_kind.tolist() == ["offensive"]
    assert f.drawn_by.tolist() == ["defender"]


def test_ft_trip_kinds():
    ev = events([
        # 1) and-one: made two then one free throw
        ("2FGM", "HOM", "h1", 500), ("RV", "HOM", "h1", 500), ("CM", "AWY", "a1", 500), ("FTM", "HOM", "h1", 500),
        # 2) three-shot trip
        ("RV", "HOM", "h2", 400), ("CM", "AWY", "a1", 400), ("FTM", "HOM", "h2", 400), ("FTM", "HOM", "h2", 400),
        ("FTA", "HOM", "h2", 400),
        # 3) two shots before the penalty (3rd team foul): certainly a shooting foul
        ("RV", "HOM", "h3", 300), ("CM", "AWY", "a1", 300), ("FTM", "HOM", "h3", 300), ("FTM", "HOM", "h3", 300),
        # 4) 4th foul with no free throws, 5) two shots at the 5th foul: ambiguous
        ("RV", "HOM", "h4", 250), ("CM", "AWY", "a2", 250),
        ("RV", "HOM", "h4", 200), ("CM", "AWY", "a2", 200), ("FTA", "HOM", "h4", 200), ("FTM", "HOM", "h4", 200),
        # 6) technical free throw by a different player
        ("CMT", "AWY", "a3", 100), ("FTM", "HOM", "h5", 100),
        # 7) unsportsmanlike foul keeps its own kind even with two shots
        ("RV", "HOM", "h6", 50), ("CMU", "AWY", "a4", 50), ("FTM", "HOM", "h6", 50), ("FTM", "HOM", "h6", 50),
    ])
    trips = ft_trips(ev, fouls_table(ev)).set_index("player_id")
    assert trips.kind.to_dict() == {"h1": "and_one", "h2": "shooting_3", "h3": "shooting_2",
                                    "h4": "shooting_or_penalty", "h5": "technical", "h6": "unsportsmanlike"}
    assert trips.loc["h2", "shots"] == 3 and trips.loc["h2", "made"] == 2
    assert trips.loc["h3", "foul_player_id"] == "a1" and trips.loc["h3", "team_fouls_at_trip"] == 3


def test_link_blocks_handles_reordered_feed_rows():
    s = pd.DataFrame([shot(2, 0, 100, seq=0, clock=500), shot(2, 0, 100, seq=3, clock=400),
                      shot(2, 0, 100, seq=5, clock=300, player="A2")])
    ev = events([("2FGA", "HOM", "A1", 500), ("AG", "HOM", "A1", 500), ("FV", "AWY", "B1", 497),  # logged 3 s later
                 ("2FGA", "HOM", "A1", 400),
                 ("FV", "AWY", "B2", 300), ("2FGA", "HOM", "A2", 300), ("D", "AWY", "B2", 300),
                 ("AG", "HOM", "A2", 299)])
    out = link_blocks(s, ev)
    assert out.blocked.tolist() == [True, False, True]
    assert out.blocker_id.tolist() == ["B1", "", "B2"]


def test_flag_rebounds():
    five = list("abcde")
    ev = events([("2FGA", "HOM", "h1", 500), ("O", "HOM", "h2", 498), ("3FGA", "HOM", "h3", 480),
                 ("O", "HOM", "", 480), ("TO", "HOM", "h3", 470),
                 ("FTA", "AWY", "a1", 300), ("O", "AWY", "", 300), ("FTM", "AWY", "a1", 300),
                 ("2FGA", "AWY", "a2", 0), ("D", "HOM", "", 0)])
    chances = ev[ev.type.isin(["O", "D"])].assign(off_lineup=[five] * 4, def_lineup=[five] * 4)
    r = flag_rebounds(chances, ev)
    assert r.team_rebound.tolist() == [False, True, True, True]
    assert r.likely_dead.tolist() == [False, False, True, True]
    assert r.prev_type.tolist() == ["2FGA", "3FGA", "FTA", "2FGA"]


def test_parse_people_keeps_latest_row_and_blanks_zero_height():
    rows = parse_people({"data": [
        {"person": {"code": "001 ", "name": "A", "height": 200, "weight": 90}, "positionName": "Guard",
         "startDate": "2025-01-01"},
        {"person": {"code": "001", "name": "A", "height": 201, "weight": 91}, "positionName": "Forward",
         "startDate": "2025-06-01"},
        {"person": {"code": "002", "name": "B", "height": 0, "weight": 0}, "positionName": "Center",
         "startDate": "2025-01-01"},
    ]}, "E2099")
    by_id = {r["player_id"]: r for r in rows}
    assert by_id["P001"]["position"] == "Forward" and by_id["P001"]["height"] == 201
    assert by_id["P002"]["height"] is None
    assert parse_people(None, "E2099") == []


def test_parse_official_maps_fields():
    rows = parse_official({"players": [{"player": {"code": "007", "name": "X"}, "gamesPlayed": 3.0,
                                        "threePointersMade": 4.0, "foulsDrawn": 1.0}]}, "E2099")
    assert rows[0]["player_id"] == "P007"
    assert (rows[0]["games"], rows[0]["fg3m"], rows[0]["fd"]) == (3.0, 4.0, 1.0)
