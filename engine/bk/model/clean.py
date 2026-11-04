"""Data-quality flags and event-derived tables built on top of the parsed tables.

Nothing is deleted or overwritten here: existing columns stay exactly as parsed,
and questionable rows only gain a flag. Rating formulas decide later what to do
with each flag.
"""

from __future__ import annotations

import pandas as pd

HEAVE_DIST_M = 12.0     # end-of-period heaves; 96% of these come with <=3 s on the clock
MIN_THREE_DIST_M = 6.5  # the arc is 6.60 m in the corners; shorter threes are bad coordinates
MAX_TWO_DIST_M = 6.75   # the arc is 6.75 m above the break; longer twos are bad coordinates
CLOCK_TOLERANCE_S = 2   # feed timestamps of linked events can differ by a second or two
BLOCK_TOLERANCE_S = 5   # the FV row is often logged 3 s after the rejected shot
# Where close shots get marked depends on the venue's scorer (near-rim median y is 43 cm in
# one arena and 175 cm in another, while the arc sits in the same place everywhere). The
# rim/paint boundary is therefore not comparable between arenas; their union is.
ZONE_GROUPS = {"rim": "inside", "paint": "inside", "mid": "mid", "corner3": "corner3",
               "above_break3": "above_break3", "unknown": "unknown", "heave": "heave"}

FOUL_KINDS = {
    "CM": "personal", "CMTI": "personal",  # CMTI = throw-in foul
    "OF": "offensive",
    "CMU": "unsportsmanlike", "CMU_FL": "unsportsmanlike", "CMU_DI": "unsportsmanlike",
    "CMD": "disqualifying",
    "CMT": "technical", "CMT1": "technical", "CMT2": "technical",
    "B": "bench", "C": "coach",
}
TEAM_FOUL_KINDS = {"personal", "offensive", "unsportsmanlike", "disqualifying", "technical"}
NON_SHOOTING_KINDS = {"unsportsmanlike", "disqualifying", "technical", "bench", "coach"}
PENALTY_FOULS = 5  # a team's 5th foul of a period onward sends a non-shooting foul to the line
GAME = ["season", "gamecode"]


def flag_shots(shots: pd.DataFrame) -> pd.DataFrame:
    """Add is_heave, coord_valid, value_dist_ok, lineup_ok, zone_clean and zone_group."""
    s = shots.copy()
    three = s.value == 3
    s["is_heave"] = three & (s.dist_m > HEAVE_DIST_M)
    s["coord_valid"] = s.x.notna() & s.y.notna() & ~((s.x == 0) & (s.y == 0))
    s["value_dist_ok"] = ~((three & (s.dist_m < MIN_THREE_DIST_M)) | (~three & (s.dist_m > MAX_TWO_DIST_M)))
    s["lineup_ok"] = s.def_lineup.map(len) == 5
    s["zone_clean"] = s.zone.where(s.coord_valid & s.value_dist_ok, "unknown").where(~s.is_heave, "heave")
    s["zone_group"] = s.zone_clean.map(ZONE_GROUPS)
    return s


def flag_possessions(possessions: pd.DataFrame) -> pd.DataFrame:
    """Add lineup_ok (5 v 5) and time_ok (the feed clock did not run backwards)."""
    p = possessions.copy()
    p["lineup_ok"] = (p.off_lineup.map(len) == 5) & (p.def_lineup.map(len) == 5)
    p["time_ok"] = p.end >= p.start
    return p


def flag_rebounds(chances: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Add neighbouring event info, team_rebound, likely_dead and lineup_ok."""
    e = events.sort_values(GAME + ["seq"])
    g = e.groupby(GAME)
    near = e[GAME + ["seq"]].assign(prev_type=g.type.shift(1), next_type=g.type.shift(-1),
                                    next_team=g.team.shift(-1), next_clock=g.clock_left.shift(-1))
    r = chances.merge(near, on=GAME + ["seq"], how="left", validate="one_to_one")
    r["team_rebound"] = r.player_id == ""
    # the same team shoots again at the same moment, or the period is over: nobody could really rebound
    between_fts = r.next_type.isin(["FTM", "FTA"]) & (r.next_team == r.team) & (r.next_clock == r.clock_left)
    r["likely_dead"] = r.team_rebound & (between_fts | (r.clock_left == 0))
    r["lineup_ok"] = (r.off_lineup.map(len) == 5) & (r.def_lineup.map(len) == 5)
    return r


def _nearest(rows: list[dict], seq: int, used: set[int]) -> dict | None:
    """Unused row closest to seq in feed order."""
    free = [r for r in rows if r["seq"] not in used]
    return min(free, key=lambda r: abs(r["seq"] - seq)) if free else None


def fouls_table(events: pd.DataFrame) -> pd.DataFrame:
    """One row per foul: kind, running team fouls in the period, and who drew it.

    The fouled player's RV row shares the foul's clock but not always its position
    in the feed, so it is matched by time and opposing team rather than adjacency.
    Overtime continues the 4th period's team-foul count.
    """
    cols = GAME + ["seq", "period", "clock_left", "team", "player_id", "type"]
    f = events[events.type.isin(FOUL_KINDS)][cols].sort_values(GAME + ["seq"]).copy()
    f["foul_kind"] = f.type.map(FOUL_KINDS)
    f["counts_team_foul"] = f.foul_kind.isin(TEAM_FOUL_KINDS)
    f["foul_period"] = f.period.clip(upper=4)
    f["team_fouls"] = f.counts_team_foul.astype(int).groupby(
        [f[c] for c in GAME + ["team", "foul_period"]]).cumsum()

    received = events[events.type == "RV"][GAME + ["seq", "period", "clock_left", "team", "player_id"]]
    pools: dict[tuple, list[dict]] = {}
    for r in received.to_dict("records"):
        pools.setdefault((r["season"], r["gamecode"], r["period"], r["clock_left"]), []).append(r)
    used: dict[tuple, set[int]] = {}
    drawn: list[str] = []
    for r in f[GAME + ["seq", "period", "clock_left", "team"]].to_dict("records"):
        key = (r["season"], r["gamecode"], r["period"], r["clock_left"])
        taken = used.setdefault(key, set())
        hit = _nearest([x for x in pools.get(key, []) if x["team"] != r["team"]], r["seq"], taken)
        if hit is not None:
            taken.add(hit["seq"])
        drawn.append(hit["player_id"] if hit is not None else "")
    f["drawn_by"] = drawn
    return f.drop(columns="foul_period").reset_index(drop=True)


def _trip_kind(n_shots: int, foul: dict | None, and_one: bool) -> str:
    if foul is not None and foul["foul_kind"] in NON_SHOOTING_KINDS:
        return "technical" if foul["foul_kind"] in {"technical", "bench", "coach"} else "unsportsmanlike"
    if n_shots == 1 and and_one:
        return "and_one"
    if n_shots == 3:
        return "shooting_3"
    if n_shots == 2:
        # below the penalty a 2-shot trip must be a shooting foul; above it, the feed cannot tell them apart
        if foul is not None and foul["team_fouls"] < PENALTY_FOULS:
            return "shooting_2"
        return "shooting_or_penalty"
    return "other"


def ft_trips(events: pd.DataFrame, fouls: pd.DataFrame) -> pd.DataFrame:
    """One row per player's free-throw trip, classified by the foul that caused it."""
    ft = events[events.type.isin(["FTM", "FTA"])]
    trips = (ft.assign(made=ft.type == "FTM")
             .groupby(GAME + ["period", "clock_left", "team", "player_id"], as_index=False)
             .agg(first_seq=("seq", "min"), shots=("seq", "size"), made=("made", "sum"))
             .sort_values(GAME + ["first_seq"]))

    foul_pool: dict[tuple, list[dict]] = {}
    for r in fouls.to_dict("records"):
        foul_pool.setdefault((r["season"], r["gamecode"], r["period"], r["clock_left"]), []).append(r)
    fgm = events[events.type.isin(["2FGM", "3FGM"])]
    makes: dict[tuple, list[int]] = {}
    for r in fgm[GAME + ["period", "player_id", "clock_left"]].itertuples(index=False):
        makes.setdefault((r.season, r.gamecode, r.period, r.player_id), []).append(r.clock_left)

    out = []
    for t in trips.to_dict("records"):
        same = foul_pool.get((t["season"], t["gamecode"], t["period"], t["clock_left"]), [])
        opp = [x for x in same if x["team"] != t["team"]]
        by_shooter = [x for x in opp if x["drawn_by"] == t["player_id"]]
        foul = _nearest(by_shooter or opp, t["first_seq"], set())
        and_one = any(abs(c - t["clock_left"]) <= CLOCK_TOLERANCE_S
                      for c in makes.get((t["season"], t["gamecode"], t["period"], t["player_id"]), []))
        out.append({**t, "kind": _trip_kind(t["shots"], foul, and_one),
                    "foul_player_id": foul["player_id"] if foul else "",
                    "foul_kind": foul["foul_kind"] if foul else "",
                    "team_fouls_at_trip": foul["team_fouls"] if foul else None})
    return pd.DataFrame(out)


def link_blocks(shots: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Add blocked and blocker_id to the shots table.

    AG ("shot rejected") belongs to the shooter and FV ("block") to the defender.
    They usually sit next to the missed shot but can be reordered in the feed, so
    each is matched by player or team and time. The block row has a wider time
    window than the shot row because it is often logged a few seconds later.
    """
    s = shots.copy()
    s["blocked"] = False
    s["blocker_id"] = ""
    misses: dict[tuple, list[dict]] = {}
    for i, r in zip(s.index[~s.made], s.loc[~s.made, GAME + ["seq", "period", "clock_left", "team", "player_id"]]
                    .to_dict("records")):
        misses.setdefault((r["season"], r["gamecode"]), []).append({**r, "idx": i})
    blocks: dict[tuple, list[dict]] = {}
    fv = events[events.type == "FV"][GAME + ["seq", "period", "clock_left", "team", "player_id"]]
    for r in fv.to_dict("records"):
        blocks.setdefault((r["season"], r["gamecode"]), []).append(r)

    rejected = events[events.type == "AG"].sort_values(GAME + ["seq"])
    used_shots: dict[tuple, set[int]] = {}
    used_blocks: dict[tuple, set[int]] = {}
    for ag in rejected[GAME + ["seq", "period", "clock_left", "team", "player_id"]].to_dict("records"):
        game = (ag["season"], ag["gamecode"])

        def close(r: dict, tolerance: int) -> bool:
            return r["period"] == ag["period"] and abs(r["clock_left"] - ag["clock_left"]) <= tolerance

        taken = used_shots.setdefault(game, set())
        shot = _nearest([r for r in misses.get(game, []) if close(r, CLOCK_TOLERANCE_S) and r["team"] == ag["team"]
                         and r["player_id"] == ag["player_id"]], ag["seq"], taken)
        if shot is None:
            continue
        taken.add(shot["seq"])
        s.loc[shot["idx"], "blocked"] = True
        taken_blocks = used_blocks.setdefault(game, set())
        block = _nearest([r for r in blocks.get(game, []) if close(r, BLOCK_TOLERANCE_S) and r["team"] != ag["team"]],
                         ag["seq"], taken_blocks)
        if block is not None:
            taken_blocks.add(block["seq"])
            s.loc[shot["idx"], "blocker_id"] = block["player_id"]
    return s


def parse_people(data: dict, season: str) -> list[dict]:
    """Latest roster row per player. A missing height or weight (0) becomes None."""
    latest: dict[str, dict] = {}
    for row in (data or {}).get("data", []):
        person = row.get("person") or {}
        pid = "P" + (person.get("code") or "").strip()
        if pid == "P":
            continue
        start = row.get("startDate") or ""
        if pid not in latest or start >= latest[pid]["start"]:
            latest[pid] = {"start": start, "season": season, "player_id": pid, "name": (person.get("name") or "").strip(),
                           "height": person.get("height") or None, "weight": person.get("weight") or None,
                           "position": row.get("positionName"), "birth_date": person.get("birthDate")}
    return [{k: v for k, v in r.items() if k != "start"} for r in latest.values()]


OFFICIAL_FIELDS = {
    "gamesPlayed": "games", "gamesStarted": "starts", "minutesPlayed": "minutes", "pointsScored": "pts",
    "twoPointersMade": "fg2m", "twoPointersAttempted": "fg2a", "threePointersMade": "fg3m",
    "threePointersAttempted": "fg3a", "freeThrowsMade": "ftm", "freeThrowsAttempted": "fta",
    "offensiveRebounds": "orb", "defensiveRebounds": "drb", "assists": "ast", "steals": "stl",
    "turnovers": "tov", "blocks": "blk", "blocksAgainst": "blk_against", "foulsCommited": "pf",
    "foulsDrawn": "fd", "pir": "pir",
}


def parse_official(data: dict, season: str) -> list[dict]:
    """Official accumulated season totals keyed like our player ids."""
    out = []
    for row in (data or {}).get("players", []):
        player = row.get("player") or {}
        pid = "P" + (player.get("code") or "").strip()
        if pid != "P":
            out.append({"season": season, "player_id": pid, "player": (player.get("name") or "").strip(),
                        **{ours: row.get(theirs) for theirs, ours in OFFICIAL_FIELDS.items()}})
    return out
