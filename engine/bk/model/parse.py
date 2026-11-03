"""Turn one game's raw JSON into tidy rows.

Everything here is pure (dicts in, lists of dicts out) so it can be unit-tested
without touching disk or network.

Conventions
-----------
* elapsed: seconds since tip-off (regulation periods 600 s, overtime 300 s).
* home = TeamA in the play-by-play feed.
* Coordinates in the Points feed are centimetres with the basket at (0, 0);
  y grows toward half court.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

PERIOD_KEYS = ("FirstQuarter", "SecondQuarter", "ThirdQuarter", "ForthQuarter")
SHOT_TYPES = {"2FGM": (2, True), "2FGA": (2, False), "3FGM": (3, True), "3FGA": (3, False)}
FT_TYPES = {"FTM": True, "FTA": False}
# events that tell us which team has the ball
OFFENSE_EVENTS = {"2FGM", "2FGA", "3FGM", "3FGA", "FTM", "FTA", "TO", "O"}
# shot context: the feed's FASTBREAK / SECOND_CHANCE flags exist only on made shots,
# so context is inferred from possession timing for makes and misses alike
TRANSITION_SECONDS = 7
PUTBACK_SECONDS = 3


def _s(v) -> str:
    return (v or "").strip()


def period_length(period: int) -> int:
    return 600 if period <= 4 else 300


def period_start(period: int) -> int:
    return 600 * min(period - 1, 4) + 300 * max(period - 5, 0)


def parse_clock(marker: str) -> int | None:
    marker = _s(marker)
    if not marker or ":" not in marker:
        return None
    m, s = marker.split(":")
    return int(m) * 60 + int(s)


def shot_zone(x: float, y: float, is3: bool) -> str:
    """Our own zone scheme derived from coordinates (stable across seasons)."""
    if is3:
        return "corner3" if (abs(x) >= 600 and y <= 200) else "above_break3"
    dist = math.hypot(x, y)
    if dist <= 125:
        return "rim"
    if abs(x) <= 245 and y <= 425:
        return "paint"
    return "mid"


def flatten_pbp(pbp: dict) -> list[tuple[int, dict]]:
    """[(period, row), ...] in feed order, overtime periods appended as 5, 6, ..."""
    out: list[tuple[int, dict]] = []
    for p, key in enumerate(PERIOD_KEYS, 1):
        out += [(p, r) for r in (pbp.get(key) or [])]
    # ExtraTime holds all OT periods concatenated; a BP after real events starts the next one
    ot, seen_play = 5, False
    for r in pbp.get("ExtraTime") or []:
        if _s(r.get("PLAYTYPE")) == "BP":
            if seen_play:
                ot, seen_play = ot + 1, False
        else:
            seen_play = True
        out.append((ot, r))
    return out


@dataclass
class GameTables:
    events: list[dict] = field(default_factory=list)
    shots: list[dict] = field(default_factory=list)
    possessions: list[dict] = field(default_factory=list)
    player_games: list[dict] = field(default_factory=list)
    stints: list[dict] = field(default_factory=list)


def _minutes(m: str) -> float:
    m = _s(m)
    if not m or m.upper() == "DNP" or ":" not in m:
        return 0.0
    a, b = m.split(":")
    return int(a) + int(b) / 60


def parse_game(season: str, gamecode: int, pbp: dict, points: dict, box: dict, meta: dict) -> GameTables:
    t = GameTables()
    home, away = _s(pbp.get("CodeTeamA")), _s(pbp.get("CodeTeamB"))
    other = {home: away, away: home}
    date = meta.get("utcDate") or meta.get("date")
    base = {"season": season, "gamecode": gamecode}

    # ---- player box lines + starters --------------------------------------
    on_court: dict[str, set[str]] = {home: set(), away: set()}
    for team_block in box.get("Stats", []):
        for p in team_block.get("PlayersStats", []):
            pid, team = _s(p["Player_ID"]), _s(p["Team"])
            mins = _minutes(p.get("Minutes"))
            if p.get("IsStarter"):
                on_court.setdefault(team, set()).add(pid)
            if mins <= 0:
                continue
            t.player_games.append({
                **base, "date": date, "team": team, "opponent": other.get(team, ""),
                "is_home": team == home, "player_id": pid, "player": _s(p["Player"]),
                "starter": bool(p.get("IsStarter")), "minutes": mins, "pts": p["Points"],
                "fg2m": p["FieldGoalsMade2"], "fg2a": p["FieldGoalsAttempted2"],
                "fg3m": p["FieldGoalsMade3"], "fg3a": p["FieldGoalsAttempted3"],
                "ftm": p["FreeThrowsMade"], "fta": p["FreeThrowsAttempted"],
                "orb": p["OffensiveRebounds"], "drb": p["DefensiveRebounds"],
                "ast": p["Assistances"], "stl": p["Steals"], "tov": p["Turnovers"],
                "blk": p["BlocksFavour"], "blk_against": p["BlocksAgainst"],
                "pf": p["FoulsCommited"], "fd": p["FoulsReceived"],
                "pir": p["Valuation"], "plus_minus": p["Plusminus"],
            })

    # ---- walk play-by-play --------------------------------------------------
    rows = flatten_pbp(pbp)
    score = {home: 0, away: 0}
    clock_left = 600
    last_period = 0
    stint_start: dict[str, float] = {}  # player -> elapsed when current stint began
    player_team: dict[str, str] = {}
    for team, ps in on_court.items():
        for pid in ps:
            stint_start[pid] = 0.0
            player_team[pid] = team

    def close_stint(pid: str, end: float) -> None:
        start = stint_start.pop(pid, None)
        if start is not None and end > start:
            t.stints.append({**base, "team": player_team.get(pid, ""), "player_id": pid,
                             "start": start, "end": end, "seconds": end - start})

    # possession tracking: runs of consecutive "offense team" labels inside a period
    poss: dict | None = None

    last_change = 0.0  # when the ball last changed hands (new possessions start here)

    def end_possession() -> None:
        nonlocal poss, last_change
        if poss is not None:
            poss.pop("last_orb", None)
            t.possessions.append(poss)
            last_change = poss["end"]
        poss = None

    shot_idx: dict[int, int] = {}  # NUMBEROFPLAY -> index into t.shots (filled below)
    pending_assist_for: int | None = None

    for seq, (period, r) in enumerate(rows):
        ptype = _s(r.get("PLAYTYPE"))
        team = _s(r.get("CODETEAM"))
        pid = _s(r.get("PLAYER_ID"))
        if period != last_period:
            end_possession()
            if last_period:
                # quarter break resets the fatigue clock: close stints at period end
                pend = period_start(last_period) + period_length(last_period)
                for p in list(stint_start):
                    close_stint(p, pend)
                    stint_start[p] = float(period_start(period))
            last_period = period
            clock_left = period_length(period)
            last_change = float(period_start(period))
        c = parse_clock(r.get("MARKERTIME"))
        if c is not None:
            clock_left = c
        elapsed = period_start(period) + period_length(period) - clock_left

        if r.get("POINTS_A") is not None and r.get("POINTS_B") is not None:
            score[home], score[away] = int(r["POINTS_A"]), int(r["POINTS_B"])

        # substitutions -------------------------------------------------------
        if ptype == "OUT" and pid:
            on_court.setdefault(team, set()).discard(pid)
            close_stint(pid, elapsed)
        elif ptype == "IN" and pid:
            on_court.setdefault(team, set()).add(pid)
            stint_start[pid] = float(elapsed)
            player_team[pid] = team

        t.events.append({**base, "seq": seq, "num": r.get("NUMBEROFPLAY"), "period": period,
                         "clock_left": clock_left, "elapsed": elapsed, "team": team,
                         "player_id": pid, "type": ptype, "home_score": score[home],
                         "away_score": score[away]})

        # possessions -----------------------------------------------------------
        off = team if ptype in OFFENSE_EVENTS else (other.get(team) if ptype == "D" else None)
        if off:
            if poss is None or poss["offense"] != off:
                end_possession()
                poss = {**base, "period": period, "offense": off, "defense": other.get(off, ""),
                        "start": last_change, "end": elapsed, "points": 0,
                        "off_lineup": sorted(on_court.get(off, set())),
                        "def_lineup": sorted(on_court.get(other.get(off, ""), set()))}
            poss["end"] = elapsed
            if ptype == "O" and team == off:
                poss["last_orb"] = elapsed
            if ptype in ("2FGM", "3FGM", "FTM") and team == off:
                poss["points"] += 2 if ptype == "2FGM" else 3 if ptype == "3FGM" else 1

        # shots: context captured at the moment of the attempt ------------------
        if ptype in SHOT_TYPES:
            margin = score[team] - score[other.get(team, "")] if team in score else 0
            shot_idx[r.get("NUMBEROFPLAY")] = len(t.shots)
            pts_before = 2 if ptype == "2FGM" else 3 if ptype == "3FGM" else 0
            poss_seconds = elapsed - poss["start"] if poss else None
            since_orb = elapsed - poss["last_orb"] if poss and "last_orb" in poss else None
            if since_orb is not None and since_orb <= PUTBACK_SECONDS:
                context = "putback"
            elif poss_seconds is not None and poss_seconds <= TRANSITION_SECONDS:
                context = "transition"
            else:
                context = "halfcourt"
            t.shots.append({
                **base, "date": date, "num": r.get("NUMBEROFPLAY"), "period": period,
                "clock_left": clock_left, "elapsed": elapsed, "team": team,
                "opponent": other.get(team, ""), "player_id": pid,
                "value": SHOT_TYPES[ptype][0], "made": SHOT_TYPES[ptype][1],
                # feed score already includes this basket; store margin *before* the shot
                "margin_before": margin - pts_before,
                "stint_seconds": elapsed - stint_start.get(pid, period_start(period)),
                "assisted": False, "assist_player_id": "",
                "poss_seconds": poss_seconds, "since_orb": since_orb, "context": context,
                "def_lineup": sorted(on_court.get(other.get(team, ""), set())),
            })
            pending_assist_for = len(t.shots) - 1 if SHOT_TYPES[ptype][1] else None
        elif ptype == "AS" and pending_assist_for is not None:
            s = t.shots[pending_assist_for]
            if s["team"] == team:
                s["assisted"], s["assist_player_id"] = True, pid
            pending_assist_for = None
        else:
            pending_assist_for = None if ptype not in ("RV", "CM") else pending_assist_for

    end_possession()
    if last_period:
        pend = period_start(last_period) + period_length(last_period)
        for p in list(stint_start):
            close_stint(p, pend)

    # ---- merge shot coordinates (Points feed links by NUM_ANOT) --------------
    for p in (points or {}).get("Rows", []):
        i = shot_idx.get(p.get("NUM_ANOT"))
        if i is None:
            continue
        s = t.shots[i]
        x, y = float(p.get("COORD_X") or 0), float(p.get("COORD_Y") or 0)
        s.update({"x": x, "y": y, "dist_m": round(math.hypot(x, y) / 100, 2),
                  "feed_zone": _s(p.get("ZONE")), "fastbreak": p.get("FASTBREAK") == "1",
                  "second_chance": p.get("SECOND_CHANCE") == "1",
                  "off_turnover": p.get("POINTS_OFF_TURNOVER") == "1"})
    for s in t.shots:
        s.setdefault("x", None)
        s.setdefault("y", None)
        s["zone"] = shot_zone(s["x"], s["y"], s["value"] == 3) if s["x"] is not None else (
            "above_break3" if s["value"] == 3 else "unknown")
    return t
