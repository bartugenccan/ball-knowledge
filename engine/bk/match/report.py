"""What the match page shows: one believable game told in full, the range behind it, and why.

Thousands of games stay under the hood. The reader gets the most typical of them, played out event by
event, the likeliest way the other side wins, and the reasons in terms of players and their ratings.
For a game already played, the real play-by-play stands next to it.
"""

from __future__ import annotations

from dataclasses import replace as dc_replace

import numpy as np

from bk.match.evaluate import inside_80, percentile
from bk.match.model import Snapshot, TeamModel
from bk.match.narrate import full_name, key_moments, narrate, quarter_summaries, short_name
from bk.match.story import coach_notes, game_story, preview, tempo_line
from bk.match.runner import Many, run_many
from bk.match.sim import GameSim, Tuning

STATS_SHOWN = ("pts", "poss", "fga", "f3a", "f3m", "f2a", "f2m", "fta", "ftm", "orb", "drb", "ast", "stl", "blk", "tov", "pf", "inside_a", "inside_m", "mid_a", "mid_m")
PLAYER_STATS = ("sec", "pts", "orb", "drb", "ast", "stl", "blk", "tov", "f3m", "f3a", "fta", "pf")
FLOW_SHOWN = ("lead_changes", "ties", "max_lead_home", "max_lead_away", "best_run_home", "best_run_away")
IMPACT_SIMS = 600
IMPACT_PLAYERS = 3
MARGIN_BINS = list(range(-40, 45, 5))


def _band(v: np.ndarray) -> dict[str, float]:
    lo, mid, hi = np.quantile(v, [0.1, 0.5, 0.9])
    return {"mean": round(float(v.mean()), 1), "lo": round(float(lo), 1), "mid": round(float(mid), 1), "hi": round(float(hi), 1)}


def ratings_index(*teams: TeamModel) -> dict[str, dict]:
    return {p.player_id: {"values": p.ratings, "labels": p.labels, "low_data": list(p.low_data)} for t in teams for p in t.players}


def team_block(m: Many, side: int) -> dict:
    t = m.team[side]
    out = {k: _band(t[k]) for k in STATS_SHOWN}
    fga = t["fga"].clip(1)
    out["efg"] = _band(100 * (t["f2m"] + 1.5 * t["f3m"]) / fga)
    out["three_pct"] = _band(100 * t["f3m"] / t["f3a"].clip(1))
    out["two_pct"] = _band(100 * t["f2m"] / t["f2a"].clip(1))
    out["ft_pct"] = _band(100 * t["ftm"] / t["fta"].clip(1))
    out["tov_rate"] = _band(100 * t["tov"] / t["poss"].clip(1))
    other = m.team[1 - side]
    out["orb_rate"] = _band(100 * t["orb"] / (t["orb"] + other["drb"]).clip(1))
    out["three_share"] = _band(100 * t["f3a"] / fga)
    out["inside_share"] = _band(100 * t["inside_a"] / fga)
    out["mid_share"] = _band(100 * t["mid_a"] / fga)
    return out


def derive_actual(team: dict, other: dict) -> dict:
    fga = max(team["fga"], 1)
    return {**team, "efg": 100 * (team["f2m"] + 1.5 * team["f3m"]) / fga, "three_pct": 100 * team["f3m"] / max(team["f3a"], 1),
            "two_pct": 100 * team["f2m"] / max(team["f2a"], 1), "ft_pct": 100 * team["ftm"] / max(team["fta"], 1),
            "tov_rate": 100 * team["tov"] / max(team["poss"], 1), "orb_rate": 100 * team["orb"] / max(team["orb"] + other["drb"], 1),
            "three_share": 100 * team["f3a"] / fga, "inside_share": 100 * team["inside_a"] / fga, "mid_share": 100 * team["mid_a"] / fga}


def players_block(m: Many, side: int, actual: dict | None) -> list[dict]:
    team = m.home if side == 0 else m.away
    cols = m.box_columns
    out = []
    for j, p in enumerate(team.players):
        row = {"player_id": p.player_id, "name": full_name(p.name), "short": short_name(p.name), "starter": p.starter, "position": p.position,
               "usual_minutes": round(p.target, 1), "ratings": p.ratings, "labels": p.labels, "low_data": list(p.low_data), "sim": {}}
        for k in PLAYER_STATS:
            v = m.players[side][:, j, cols.index(k)]
            if k == "sec":
                v = v / 60
            row["sim"]["min" if k == "sec" else k] = _band(v)
        reb = m.players[side][:, j, cols.index("orb")] + m.players[side][:, j, cols.index("drb")]
        row["sim"]["reb"] = _band(reb)
        if actual:
            real = actual["players"].get(p.player_id)
            if real:
                row["actual"] = {"min": round(real["sec"] / 60, 1), "pts": real["pts"], "reb": real["orb"] + real["drb"], "ast": real["ast"], "stl": real["stl"],
                                 "blk": real["blk"], "tov": real["tov"], "f3m": real["f3m"], "f3a": real["f3a"], "fta": real["fta"], "pf": real["pf"]}
                row["in_range"] = {"min": inside_80(m.players[side][:, j, cols.index("sec")] / 60, real["sec"] / 60),
                                   "pts": inside_80(m.players[side][:, j, cols.index("pts")], real["pts"]),
                                   "reb": inside_80(reb, real["orb"] + real["drb"]),
                                   "ast": inside_80(m.players[side][:, j, cols.index("ast")], real["ast"])}
        out.append(row)
    out.sort(key=lambda r: -r["sim"]["min"]["mean"])
    return out


def typical_game(m: Many, winner_side: int | None = None) -> int:
    """The simulated game closest to the middle on score, flow and how the main players did."""
    margin = m.home_pts - m.away_pts
    total = m.home_pts + m.away_pts
    parts = [margin, total, m.flow["lead_changes"], m.flow["max_lead_home"], m.flow["max_lead_away"]]
    weights = [3.0, 1.5, 1.0, 0.5, 0.5]
    cols = m.box_columns
    for side in (0, 1):
        pts = m.players[side][:, :, cols.index("pts")]
        top = np.argsort(-pts.mean(axis=0))[:4]
        for j in top:
            parts.append(pts[:, j])
            weights.append(0.6)
    scores = np.zeros(m.n)
    for x, w in zip(parts, weights):
        sd = x.std() or 1.0
        scores += w * ((x - np.median(x)) / sd) ** 2
    if winner_side is not None:
        wins = margin > 0 if winner_side == 0 else margin < 0
        if wins.any():
            scores = np.where(wins, scores, np.inf)
    return int(np.argmin(scores))


def play_again(m: Many, league: dict, tune: Tuning | None, seed: int, index: int, neutral: bool, ratings: dict) -> dict:
    """Replays one game of the batch with its events kept. Same seed, same game."""
    g = GameSim(m.home, m.away, league, tune, seed=seed + index, trace=True, neutral=neutral, expected_margin=m.expected).play()
    home, away = m.home.code, m.away.code
    box = []
    for s in g.sides:
        team_rows = []
        for p, b in zip(s.model.players, s.box):
            if b[0] <= 0:
                continue
            team_rows.append({"player_id": p.player_id, "name": short_name(p.name), "min": round(b[0] / 60, 1), "pts": b[1], "reb": b[8] + b[9], "ast": b[10],
                              "stl": b[11], "blk": b[12], "tov": b[13], "pf": b[14], "f2": f"{b[2]}/{b[3]}", "f3": f"{b[4]}/{b[5]}", "ft": f"{b[6]}/{b[7]}"})
        team_rows.sort(key=lambda r: -r["min"])
        box.append(team_rows)
    events = narrate(g.events, ratings)
    moments = key_moments(g.events, home, away)
    periods = quarter_summaries(g.events, home, away)
    return {"index": index, "home": g.sides[0].pts, "away": g.sides[1].pts, "quarters": g.quarters, "margins": g.margins[:41],
            "lead_changes": g.lead_changes, "ties": g.ties, "max_lead": g.max_lead, "best_run": g.best_run,
            "overtime": len(g.quarters) > 4, "box": box, "events": events, "moments": moments, "periods": periods,
            "story": game_story(events, periods, moments, home, away)}


def _leaders(team: TeamModel, attribute: str, count: int = 2) -> list[dict]:
    """The regulars who lead a team on one rating."""
    regulars = [p for p in team.players if p.target >= 12 and attribute in p.ratings and attribute not in p.low_data]
    regulars.sort(key=lambda p: -p.ratings[attribute])
    return [{"name": short_name(p.name), "rating": p.ratings[attribute], "label": p.labels.get(attribute)} for p in regulars[:count]]


def edges(m: Many) -> list[dict]:
    """Where one side gets its points from, in points, each tied to the players the ratings single out."""
    h, a = m.team[0], m.team[1]
    mean = lambda x: float(np.mean(x))  # noqa: E731
    league_ppp = (mean(h["pts"]) + mean(a["pts"])) / max(mean(h["poss"]) + mean(a["poss"]), 1)
    efg_h = 100 * mean(h["f2m"] + 1.5 * h["f3m"]) / mean(h["fga"])
    efg_a = 100 * mean(a["f2m"] + 1.5 * a["f3m"]) / mean(a["fga"])
    fga = (mean(h["fga"]) + mean(a["fga"])) / 2
    orb_h = 100 * mean(h["orb"]) / mean(h["orb"] + a["drb"])
    orb_a = 100 * mean(a["orb"]) / mean(a["orb"] + h["drb"])
    tov_h, tov_a = mean(h["tov"]), mean(a["tov"])
    rows = [
        {"key": "shooting", "label": "Şut verimi (eFG%)", "home": round(efg_h, 1), "away": round(efg_a, 1), "unit": "%",
         "points": round(fga * 2 * (efg_h - efg_a) / 100, 1), "attribute": "three_point", "attribute2": "finishing"},
        {"key": "turnovers", "label": "Top kaybı", "home": round(tov_h, 1), "away": round(tov_a, 1), "unit": "",
         "points": round((tov_a - tov_h) * league_ppp, 1), "attribute": "steals", "attribute2": None},
        {"key": "rebounds", "label": "Hücum ribaundu payı", "home": round(orb_h, 1), "away": round(orb_a, 1), "unit": "%",
         "points": round((mean(h["orb"]) - mean(a["orb"])) * league_ppp, 1), "attribute": "off_rebounding", "attribute2": "def_rebounding"},
        {"key": "free_throws", "label": "Giren serbest atış", "home": round(mean(h["ftm"]), 1), "away": round(mean(a["ftm"]), 1), "unit": "",
         "points": round(mean(h["ftm"]) - mean(a["ftm"]), 1), "attribute": "drawing_fouls", "attribute2": "free_throw"},
    ]
    for r in rows:
        keys = [k for k in (r.pop("attribute"), r.pop("attribute2")) if k]
        r["leaders"] = {m.home.code: [x | {"attribute": k} for k in keys for x in _leaders(m.home, k, 1)],
                        m.away.code: [x | {"attribute": k} for k in keys for x in _leaders(m.away, k, 1)]}
    return rows


def what_if_other_side(m: Many) -> dict:
    """The games the less likely side wins, against the rest: what had to go differently."""
    margin = m.home_pts - m.away_pts
    home_wins = margin > 0
    home_favored = home_wins.mean() >= 0.5
    upset = ~home_wins if home_favored else home_wins
    if upset.sum() < 20:
        return {"share": round(float(upset.mean()), 3), "rows": []}
    side = 1 if home_favored else 0
    team = m.away if home_favored else m.home
    rows = []

    def add(label: str, values: np.ndarray, kind: str, digits: int = 1) -> None:
        a, b = float(values[upset].mean()), float(values[~upset].mean())
        rows.append({"label": label, "upset": round(a, digits), "usual": round(b, digits), "kind": kind})

    for s, code in ((side, team.code), (1 - side, (m.home if side == 1 else m.away).code)):
        t = m.team[s]
        add(f"{code} üçlük %", 100 * t["f3m"] / t["f3a"].clip(1), "team")
        add(f"{code} iki sayılık %", 100 * t["f2m"] / t["f2a"].clip(1), "team")
        add(f"{code} top kaybı", t["tov"], "team")
        add(f"{code} hücum ribaundu", t["orb"], "team")
    cols = m.box_columns
    pts = m.players[side][:, :, cols.index("pts")]
    diffs = [(float(pts[:, j][upset].mean() - pts[:, j][~upset].mean()), j) for j in range(pts.shape[1])]
    for gap, j in sorted(diffs, reverse=True)[:3]:
        if gap >= 1.0:
            add(f"{short_name(team.players[j].name)} sayı", pts[:, j], "player")
    rows.sort(key=lambda r: -abs(r["upset"] - r["usual"]) if r["kind"] == "player" else 0)
    return {"team": team.code, "share": round(float(upset.mean()), 3), "rows": rows}


WHAT_IF_SIMS = 1500
WHAT_IF_SE = 0.6        # about the error of a difference between two such runs, in points


def _changed(team: TeamModel, label: str) -> TeamModel:
    """The same team with one thing done a little better."""
    players = []
    for p in team.players:
        if label == "turnovers":
            players.append(dc_replace(p, tov=p.tov * 0.85))
        elif label == "offensive_rebounds":
            players.append(dc_replace(p, orb=p.orb * 1.15))
        elif label == "defensive_rebounds":
            players.append(dc_replace(p, drb=p.drb * 1.10))
        elif label == "free_throws":
            players.append(dc_replace(p, trip=p.trip * 1.15, fd=p.fd * 1.15))
        elif label == "threes":
            players.append(dc_replace(p, make={**p.make, "corner3": p.make["corner3"] + 0.09, "above_break3": p.make["above_break3"] + 0.09}))
        else:
            raise ValueError(label)
    return dc_replace(team, players=players)


WHAT_IF_LABELS = {"turnovers": "Top kaybını %15 azaltmak", "offensive_rebounds": "Hücum ribaundunu %15 artırmak", "defensive_rebounds": "Savunma ribaundunu %10 artırmak",
                  "free_throws": "Çizgiye %15 daha çok gitmek", "threes": "Üçlük isabetini 2 puan artırmak"}


def what_if(home: TeamModel, away: TeamModel, league: dict, tune: Tuning | None, seed: int, neutral: bool = False) -> list[dict]:
    """What each side's result depends on: the game replayed with one thing changed. Mechanical, not a plan to get there."""
    base = run_many(home, away, league, tune, WHAT_IF_SIMS, seed, neutral)
    base_margin = float((base.home_pts - base.away_pts).mean())
    out = []
    for side, team in ((0, home), (1, away)):
        for key, label in WHAT_IF_LABELS.items():
            changed = _changed(team, key)
            pair = (changed, away) if side == 0 else (home, changed)
            alt = run_many(pair[0], pair[1], league, tune, WHAT_IF_SIMS, seed, neutral)
            gain = float((alt.home_pts - alt.away_pts).mean()) - base_margin
            gain = gain if side == 0 else -gain
            out.append({"team": team.code, "key": key, "label": label, "margin": round(gain, 1), "significant": gain >= 2 * WHAT_IF_SE})
    return out


def build_report(snap: Snapshot, home: TeamModel, away: TeamModel, tune: Tuning | None = None, sims: int = 2000,
                 seed: int = 0, neutral: bool = False, actual: dict | None = None, with_coach: bool = True) -> dict:
    league = snap.league
    m = run_many(home, away, league, tune, sims, seed, neutral)
    margin = m.home_pts - m.away_pts
    hist, _ = np.histogram(margin, bins=MARGIN_BINS)
    favored = 0 if m.home_win >= 0.5 else 1
    ratings = ratings_index(home, away)
    typical = play_again(m, league, tune, seed, typical_game(m, favored), neutral, ratings)
    other = play_again(m, league, tune, seed, typical_game(m, 1 - favored), neutral, ratings)
    bands = np.quantile(m.margins, [0.1, 0.5, 0.9], axis=0)
    quarter_points = np.diff(m.quarters, axis=1, prepend=0)
    report = {
        "home": {"code": home.code, "name": home.name}, "away": {"code": away.code, "name": away.name}, "neutral": neutral,
        "sims": sims, "home_win": round(m.home_win, 3), "overtime_share": round(float(m.overtime.mean()), 3),
        "score": {"home": _band(m.home_pts), "away": _band(m.away_pts), "margin": _band(margin), "total": _band(m.home_pts + m.away_pts)},
        "margin_histogram": {"bins": MARGIN_BINS, "counts": [int(x) for x in hist]},
        "minute_band": {"lo": [round(float(x), 1) for x in bands[0]], "mid": [round(float(x), 1) for x in bands[1]], "hi": [round(float(x), 1) for x in bands[2]]},
        "quarters": {"home": [round(float(x), 1) for x in quarter_points[:, :, 0].mean(axis=0)], "away": [round(float(x), 1) for x in quarter_points[:, :, 1].mean(axis=0)]},
        "flow": {k: _band(m.flow[k]) for k in FLOW_SHOWN},
        "teams": {home.code: team_block(m, 0), away.code: team_block(m, 1)},
        "players": {home.code: players_block(m, 0, actual), away.code: players_block(m, 1, actual)},
        "edges": edges(m), "other_side": what_if_other_side(m),
        "typical": typical, "other": other,
    }
    report["preview"] = preview(report)
    report["tempo"] = tempo_line(report)
    if with_coach:
        report["what_if"] = what_if(home, away, league, tune, seed + 500_000, neutral)
        report["coach"] = coach_notes(report, report["what_if"])
    if actual:
        report["comparison"] = compare(m, actual)
    return report


def compare(m: Many, actual: dict) -> dict:
    """The real game against the simulated range, and where the difference came from."""
    home, away = m.home.code, m.away.code
    real = {home: derive_actual(actual["team"][0], actual["team"][1]), away: derive_actual(actual["team"][1], actual["team"][0])}
    table = []
    for k in ("pts", "poss", "efg", "three_pct", "two_pct", "f3a", "inside_a", "mid_a", "fta", "tov", "orb", "drb", "ast", "stl", "blk", "pf"):
        for side, code in ((0, home), (1, away)):
            t = m.team[side]
            if k == "efg":
                v = 100 * (t["f2m"] + 1.5 * t["f3m"]) / t["fga"].clip(1)
            elif k == "three_pct":
                v = 100 * t["f3m"] / t["f3a"].clip(1)
            elif k == "two_pct":
                v = 100 * t["f2m"] / t["f2a"].clip(1)
            else:
                v = t[k]
            table.append({"stat": k, "team": code, "real": round(float(real[code][k]), 1), **_band(v), "in_range": inside_80(v, real[code][k]),
                          "percentile": round(percentile(v, real[code][k]), 2)})
    flow_rows = []
    for k in FLOW_SHOWN:
        flow_rows.append({"stat": k, "real": actual["flow"][k], **_band(m.flow[k]), "in_range": inside_80(m.flow[k], actual["flow"][k])})

    # where the score gap came from: for each side, volume against accuracy, in points
    gaps = []
    for side, code in ((0, home), (1, away)):
        t, r = m.team[side], real[code]
        p2 = float(t["f2m"].mean() / max(t["f2a"].mean(), 1))
        p3 = float(t["f3m"].mean() / max(t["f3a"].mean(), 1))
        a2, a3 = float(t["f2a"].mean()), float(t["f3a"].mean())
        gaps += [
            {"team": code, "kind": "three_accuracy", "points": round(r["f3a"] * (r["f3m"] / max(r["f3a"], 1) - p3) * 3, 1), "expected": round(100 * p3, 1), "real": round(r["three_pct"], 1)},
            {"team": code, "kind": "two_accuracy", "points": round(r["f2a"] * (r["f2m"] / max(r["f2a"], 1) - p2) * 2, 1), "expected": round(100 * p2, 1), "real": round(r["two_pct"], 1)},
            {"team": code, "kind": "three_volume", "points": round((r["f3a"] - a3) * p3 * 3, 1), "expected": round(a3, 1), "real": r["f3a"]},
            {"team": code, "kind": "two_volume", "points": round((r["f2a"] - a2) * p2 * 2, 1), "expected": round(a2, 1), "real": r["f2a"]},
            {"team": code, "kind": "free_throws", "points": round(r["ftm"] - float(t["ftm"].mean()), 1), "expected": round(float(t["ftm"].mean()), 1), "real": r["ftm"]},
        ]
    gaps.sort(key=lambda g: -abs(g["points"]))
    hp, ap = actual["team"][0]["pts"], actual["team"][1]["pts"]
    lo, hi = np.quantile(m.margins, [0.1, 0.9], axis=0)
    curve = np.array(actual["flow"]["margins"])
    margin = m.home_pts - m.away_pts
    return {"home": hp, "away": ap, "quarters": actual["quarters"], "overtime": actual["overtime"],
            "favored_won": (m.home_win >= 0.5) == (hp > ap),
            "margin_in_range": inside_80(margin, hp - ap), "margin_percentile": round(percentile(margin, hp - ap), 2),
            "total_in_range": inside_80(m.home_pts + m.away_pts, hp + ap),
            "margins": actual["flow"]["margins"], "minutes_in_band": round(float(np.mean((curve >= lo) & (curve <= hi))), 3),
            "teams": real, "table": table, "flow": flow_rows, "gaps": gaps, "subs": actual["subs"],
            "subs_sim": [round(float(m.subs[:, 0].mean()), 1), round(float(m.subs[:, 1].mean()), 1)]}


def _clock_text(left: float) -> str:
    whole = int(left)
    return f"{whole // 60}:{whole % 60:02d}"


def real_events(t, season: str, gamecode: int, home: str, away: str) -> list[dict]:
    """The real play-by-play, in the shape the simulator logs."""
    ev = t.events[(t.events.season == season) & (t.events.gamecode == gamecode)].sort_values("seq")
    pg = t.player_games[(t.player_games.season == season) & (t.player_games.gamecode == gamecode)]
    names = dict(zip(pg.player_id, pg.player))
    sh = t.shots[(t.shots.season == season) & (t.shots.gamecode == gamecode)].set_index("seq")
    fouls = t.fouls[(t.fouls.season == season) & (t.fouls.gamecode == gamecode)].set_index("seq")
    rows = list(ev.itertuples())
    out: list[dict] = []
    h, a = 0, 0
    fouls_by_player: dict[str, int] = {}
    i = 0
    n = len(rows)

    def base(r, event: str, **data) -> dict:
        return {"event": event, "period": int(r.period), "clock": _clock_text(r.clock_left), "elapsed": float(r.elapsed), "team": r.team or None,
                "home": h, "away": a, **data}

    while i < n:
        r = rows[i]
        kind = r.type
        pid = r.player_id
        name = names.get(pid, pid) if pid else ""
        if kind in ("2FGM", "3FGM", "2FGA", "3FGA"):
            shot = sh.loc[r.seq] if r.seq in sh.index else None
            made = kind.endswith("M")
            value = 3 if kind[0] == "3" else 2
            if made:
                if r.team == home:
                    h += value
                else:
                    a += value
            zone = None
            context = "halfcourt"
            assist = blocker = blocker_id = coord = None
            if shot is not None:
                zone = shot.zone_group
                context = shot.context
                if bool(shot.assisted) and shot.assist_player_id:
                    assist = names.get(shot.assist_player_id)
                if bool(shot.blocked) and shot.blocker_id:
                    blocker, blocker_id = names.get(shot.blocker_id), shot.blocker_id
                if bool(shot.coord_valid):
                    coord = (round(float(shot.x)), round(float(shot.y)))
            if zone not in ("inside", "mid", "corner3", "above_break3"):
                zone = "above_break3" if value == 3 else "inside"
            if made:
                out.append(base(r, "make", player=name, player_id=pid, zone=zone, value=value, context=context, assist=assist,
                                assist_id=None, coord=coord))
            else:
                out.append(base(r, "miss", player=name, player_id=pid, zone=zone, value=value, context=context, blocked_by=blocker,
                                blocked_by_id=blocker_id, coord=coord))
        elif kind in ("FTM", "FTA"):
            made, shots, j = 0, 0, i
            while j < n and rows[j].type in ("FTM", "FTA") and rows[j].player_id == pid and rows[j].elapsed == r.elapsed:
                shots += 1
                if rows[j].type == "FTM":
                    made += 1
                j += 1
            if r.team == home:
                h += made
            else:
                a += made
            out.append(base(r, "ft", player=name, player_id=pid, made=made, shots=shots))
            i = j
            continue
        elif kind == "D" and pid:
            out.append(base(r, "drb", player=name, player_id=pid))
        elif kind == "O" and pid:
            out.append(base(r, "orb", player=name, player_id=pid))
        elif kind == "ST":
            lost = next((rows[j] for j in range(max(0, i - 1), min(n, i + 2)) if rows[j].type == "TO" and rows[j].clock_left == r.clock_left), None)
            out.append(base(r, "steal", player=name, player_id=pid, lost_by=names.get(lost.player_id) if lost is not None else None))
        elif kind == "TO":
            has_steal = any(rows[j].type == "ST" and rows[j].clock_left == r.clock_left for j in range(max(0, i - 1), min(n, i + 2)))
            offensive = any(rows[j].type == "OF" and rows[j].clock_left == r.clock_left for j in range(max(0, i - 2), min(n, i + 3)))
            if not has_steal and pid:
                fouls_now = fouls_by_player.get(pid, 0)
                out.append(base(r, "turnover", player=name, player_id=pid, kind="offensive_foul" if offensive else "other", fouls=fouls_now + 1 if offensive else None))
        elif kind == "OF":
            fouls_by_player[pid] = fouls_by_player.get(pid, 0) + 1
        elif kind in ("CM", "CMU", "CMT", "CMD", "CMT1", "CMT2", "CMU_DI", "CMU_FL", "CMTI") and pid:
            fouls_by_player[pid] = fouls_by_player.get(pid, 0) + 1
            drawn = fouls.loc[r.seq].drawn_by if r.seq in fouls.index else ""
            if not isinstance(drawn, str):
                drawn = drawn.iloc[0] if len(drawn) else ""
            team_fouls = fouls.loc[r.seq].team_fouls if r.seq in fouls.index else 0
            if not np.isscalar(team_fouls):
                team_fouls = team_fouls.iloc[0]
            out.append(base(r, "foul", player=name, player_id=pid, drawn=names.get(drawn) if drawn else None, fouls=fouls_by_player[pid],
                            kind="penalty" if team_fouls and team_fouls > 4 else "personal"))
        elif kind in ("IN", "OUT"):
            into, away_from, j = [], [], i
            while j < n and rows[j].type in ("IN", "OUT") and rows[j].team == r.team and rows[j].clock_left == r.clock_left:
                (into if rows[j].type == "IN" else away_from).append(names.get(rows[j].player_id, rows[j].player_id))
                j += 1
            if into and away_from:
                out.append(base(r, "sub", into=into, out=away_from, reason=""))
            i = j
            continue
        elif kind == "TOUT":
            out.append(base(r, "timeout", run=0))
        elif kind == "TOUT_TV":
            out.append(base(r, "tv_timeout", team=None))
        elif kind == "BP":
            out.append(base(r, "period_start"))
        elif kind == "EP":
            out.append(base(r, "period_end"))
        i += 1
    return out


def real_block(events: list[dict], home: str, away: str, ratings: dict) -> dict:
    """A played game told the same way as a simulated one."""
    told = narrate(events, ratings)
    moments = key_moments(events, home, away)
    periods = quarter_summaries(events, home, away)
    return {"events": told, "moments": moments, "periods": periods, "story": game_story(told, periods, moments, home, away)}


def compare_saved(rep: dict, actual: dict) -> dict:
    """A locked prediction against the real game, from the ranges stored with it."""
    home, away = rep["home"]["code"], rep["away"]["code"]
    real = {home: derive_actual(actual["team"][0], actual["team"][1]), away: derive_actual(actual["team"][1], actual["team"][0])}
    inside = lambda band, x: band["lo"] <= x <= band["hi"]  # noqa: E731
    table = []
    for k in ("pts", "poss", "efg", "three_pct", "two_pct", "f3a", "inside_a", "mid_a", "fta", "tov", "orb", "drb", "ast", "stl", "blk", "pf"):
        for code in (home, away):
            band = rep["teams"][code][k]
            table.append({"stat": k, "team": code, "real": round(float(real[code][k]), 1), **band, "in_range": inside(band, real[code][k])})
    flow = [{"stat": k, "real": actual["flow"][k], **rep["flow"][k], "in_range": inside(rep["flow"][k], actual["flow"][k])} for k in FLOW_SHOWN]

    gaps = []
    for code in (home, away):
        t, r = rep["teams"][code], real[code]
        a2, a3 = t["f2a"]["mean"], t["f3a"]["mean"]
        p2, p3 = t["f2m"]["mean"] / max(a2, 1), t["f3m"]["mean"] / max(a3, 1)
        gaps += [
            {"team": code, "kind": "three_accuracy", "points": round(r["f3a"] * (r["f3m"] / max(r["f3a"], 1) - p3) * 3, 1), "expected": round(100 * p3, 1), "real": round(r["three_pct"], 1)},
            {"team": code, "kind": "two_accuracy", "points": round(r["f2a"] * (r["f2m"] / max(r["f2a"], 1) - p2) * 2, 1), "expected": round(100 * p2, 1), "real": round(r["two_pct"], 1)},
            {"team": code, "kind": "three_volume", "points": round((r["f3a"] - a3) * p3 * 3, 1), "expected": round(a3, 1), "real": r["f3a"]},
            {"team": code, "kind": "two_volume", "points": round((r["f2a"] - a2) * p2 * 2, 1), "expected": round(a2, 1), "real": r["f2a"]},
            {"team": code, "kind": "free_throws", "points": round(r["ftm"] - t["ftm"]["mean"], 1), "expected": round(t["ftm"]["mean"], 1), "real": r["ftm"]},
        ]
    gaps.sort(key=lambda g: -abs(g["points"]))

    named = set()
    for code in (home, away):
        for p in rep["players"][code]:
            named.add(p["player_id"])
            got = actual["players"].get(p["player_id"])
            if got is None:
                continue
            reb = got["orb"] + got["drb"]
            p["actual"] = {"min": round(got["sec"] / 60, 1), "pts": got["pts"], "reb": reb, "ast": got["ast"], "stl": got["stl"], "blk": got["blk"], "tov": got["tov"], "f3m": got["f3m"], "f3a": got["f3a"], "fta": got["fta"], "pf": got["pf"]}
            p["in_range"] = {"min": inside(p["sim"]["min"], got["sec"] / 60), "pts": inside(p["sim"]["pts"], got["pts"]), "reb": inside(p["sim"]["reb"], reb), "ast": inside(p["sim"]["ast"], got["ast"])}
    hp, ap = actual["team"][0]["pts"], actual["team"][1]["pts"]
    lo, hi = np.array(rep["minute_band"]["lo"]), np.array(rep["minute_band"]["hi"])
    curve = np.array(actual["flow"]["margins"])
    return {"home": hp, "away": ap, "quarters": actual["quarters"], "overtime": actual["overtime"], "favored_won": (rep["home_win"] >= 0.5) == (hp > ap),
            "margin_in_range": inside(rep["score"]["margin"], hp - ap), "total_in_range": inside(rep["score"]["total"], hp + ap),
            "margins": actual["flow"]["margins"], "minutes_in_band": round(float(np.mean((curve >= lo) & (curve <= hi))), 3), "teams": real, "table": table, "flow": flow, "gaps": gaps,
            "subs": actual["subs"], "missing_players": sum(1 for pid, x in actual["players"].items() if pid not in named and x["sec"] > 0)}
