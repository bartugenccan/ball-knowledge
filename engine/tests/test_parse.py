from bk.model.parse import flatten_pbp, parse_game, shot_zone


def ev(num, ptype, team, pid, clock, a=None, b=None):
    return {"NUMBEROFPLAY": num, "PLAYTYPE": ptype, "CODETEAM": team + "   ", "PLAYER_ID": pid + "  ",
            "MARKERTIME": clock, "POINTS_A": a, "POINTS_B": b, "PLAYER": pid, "PLAYINFO": ""}


def box_player(pid, team, starter, minutes="05:00", **kw):
    base = {"Player_ID": pid, "IsStarter": int(starter), "Team": team, "Player": pid, "Minutes": minutes,
            "Points": 0, "FieldGoalsMade2": 0, "FieldGoalsAttempted2": 0, "FieldGoalsMade3": 0,
            "FieldGoalsAttempted3": 0, "FreeThrowsMade": 0, "FreeThrowsAttempted": 0, "OffensiveRebounds": 0,
            "DefensiveRebounds": 0, "TotalRebounds": 0, "Assistances": 0, "Steals": 0, "Turnovers": 0,
            "BlocksFavour": 0, "BlocksAgainst": 0, "FoulsCommited": 0, "FoulsReceived": 0, "Valuation": 0,
            "Plusminus": 0}
    base.update(kw)
    return base


def make_game():
    home = [f"H{i}" for i in range(1, 7)]
    away = [f"A{i}" for i in range(1, 6)]
    box = {"Stats": [
        {"PlayersStats": [box_player(p, "HOM", i < 5) for i, p in enumerate(home)]},
        {"PlayersStats": [box_player(p, "AWY", True) for p in away]},
    ]}
    q1 = [
        ev(1, "BP", "", "", ""),
        ev(2, "3FGM", "HOM", "H1", "09:40", 3, 0),   # assisted three by H1
        ev(3, "AS", "HOM", "H2", "09:40"),
        ev(4, "2FGA", "AWY", "A1", "09:20"),
        ev(5, "O", "AWY", "A5", "09:18"),           # offensive rebound keeps the possession
        ev(6, "2FGM", "AWY", "A5", "09:17", 3, 2),
        ev(7, "OUT", "HOM", "H5", "08:00"),
        ev(8, "IN", "HOM", "H6", "08:00"),
        ev(9, "2FGA", "HOM", "H6", "07:30"),
        ev(10, "D", "AWY", "A2", "07:28"),          # defensive rebound ends HOM possession
        ev(11, "TO", "AWY", "A2", "07:00"),
        ev(12, "EP", "", "", "00:00"),
    ]
    pbp = {"CodeTeamA": "HOM", "CodeTeamB": "AWY", "FirstQuarter": q1, "SecondQuarter": [], "ThirdQuarter": [],
           "ForthQuarter": [], "ExtraTime": []}
    points = {"Rows": [{"NUM_ANOT": 2, "COORD_X": 650, "COORD_Y": 100, "ZONE": "H", "FASTBREAK": "0",
                        "SECOND_CHANCE": "0", "POINTS_OFF_TURNOVER": "0"},
                       {"NUM_ANOT": 6, "COORD_X": 10, "COORD_Y": 20, "ZONE": "A", "FASTBREAK": "0",
                        "SECOND_CHANCE": "1", "POINTS_OFF_TURNOVER": "0"}]}
    return parse_game("E2099", 1, pbp, points, box, {"utcDate": "2099-10-01T18:00:00Z"})


def test_shots_assists_and_context():
    t = make_game()
    assert [s["player_id"] for s in t.shots] == ["H1", "A1", "A5", "H6"]
    three = t.shots[0]
    assert three["assisted"] and three["assist_player_id"] == "H2"
    assert three["zone"] == "corner3" and three["margin_before"] == 0
    put = t.shots[2]
    assert put["second_chance"] and put["zone"] == "rim" and not put["assisted"]
    assert put["margin_before"] == -3  # AWY trailed 0-3 before the putback
    assert [s["context"] for s in t.shots] == ["halfcourt", "halfcourt", "putback", "halfcourt"]
    late = [s for s in t.shots if s["player_id"] == "H6"][0]
    assert late["stint_seconds"] == 30  # subbed in at 08:00, shot at 07:30
    assert all(len(s["def_lineup"]) == 5 for s in t.shots)


def test_possessions_follow_ball():
    t = make_game()
    offs = [p["offense"] for p in t.possessions]
    assert offs == ["HOM", "AWY", "HOM", "AWY"]
    assert [p["points"] for p in t.possessions] == [3, 2, 0, 0]
    assert "H6" in t.possessions[2]["off_lineup"] and "H5" not in t.possessions[2]["off_lineup"]


def test_shots_carry_their_possession_number():
    t = make_game()
    assert [p["poss_no"] for p in t.possessions] == [0, 1, 2, 3]
    assert [s["poss_no"] for s in t.shots] == [0, 1, 1, 2]  # the putback stays in the same possession


def test_stints_cover_substitution():
    t = make_game()
    h5 = [s for s in t.stints if s["player_id"] == "H5"]
    h6 = [s for s in t.stints if s["player_id"] == "H6"]
    assert h5 == [{**h5[0], "start": 0.0, "end": 120}]
    assert h6[0]["start"] == 120 and h6[0]["end"] == 600


def test_rebound_chances_record_both_lineups_at_that_moment():
    t = make_game()
    first, second = t.rebound_chances
    assert (first["type"], first["team"], first["offense"], first["defense"]) == ("O", "AWY", "AWY", "HOM")
    assert "H5" in first["def_lineup"] and "H6" not in first["def_lineup"]  # before the substitution
    assert (second["type"], second["team"], second["offense"], second["defense"]) == ("D", "AWY", "HOM", "AWY")
    assert "H6" in second["off_lineup"] and "H5" not in second["off_lineup"]  # after the substitution


def test_overtime_periods_split_on_begin_period():
    pbp = {"ExtraTime": [ev(1, "BP", "", "", ""), ev(2, "2FGA", "X", "P", "04:00"), ev(3, "EP", "", "", ""),
                         ev(4, "BP", "", "", ""), ev(5, "2FGA", "X", "P", "04:00")]}
    periods = [p for p, _ in flatten_pbp(pbp)]
    assert periods == [5, 5, 5, 6, 6]


def test_substitutions_before_begin_period_do_not_create_an_overtime():
    pbp = {"ExtraTime": [ev(1, "IN", "X", "P", "05:00"), ev(2, "OUT", "X", "Q", "05:00"), ev(3, "BP", "", "", ""),
                         ev(4, "2FGA", "X", "P", "04:00"), ev(5, "EP", "", "", ""), ev(6, "EG", "", "", "")]}
    assert [p for p, _ in flatten_pbp(pbp)] == [5, 5, 5, 5, 5, 5]


def test_rows_after_end_period_belong_to_the_next_overtime():
    pbp = {"ExtraTime": [ev(1, "BP", "", "", ""), ev(2, "2FGA", "X", "P", "04:00"), ev(3, "EP", "", "", ""),
                         ev(4, "IN", "X", "P", "05:00"), ev(5, "BP", "", "", ""), ev(6, "2FGA", "X", "P", "04:00"),
                         ev(7, "EP", "", "", ""), ev(8, "EG", "", "", "")]}
    assert [p for p, _ in flatten_pbp(pbp)] == [5, 5, 5, 6, 6, 6, 6, 6]


def test_zones():
    assert shot_zone(0, 50, False) == "rim"
    assert shot_zone(100, 300, False) == "paint"
    assert shot_zone(400, 300, False) == "mid"
    assert shot_zone(-670, 50, True) == "corner3"
    assert shot_zone(0, 700, True) == "above_break3"
