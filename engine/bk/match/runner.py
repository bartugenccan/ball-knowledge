"""Play a game many times, and read a real game into the same shape so the two can be compared."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from bk.match.model import TeamModel
from bk.match.sim import AST, BLK, DRB, F2A, F2M, F3A, F3M, FTA, FTM, GameSim, ORB, PF, PTS, SEC, SELF, STL, TOV, Tuning

BOX_INDEX = {"sec": SEC, "pts": PTS, "f2m": F2M, "f2a": F2A, "f3m": F3M, "f3a": F3A, "ftm": FTM, "fta": FTA, "orb": ORB,
             "drb": DRB, "ast": AST, "stl": STL, "blk": BLK, "tov": TOV, "pf": PF, "self": SELF}
TEAM_STATS = ("pts", "poss", "fga", "f2a", "f3a", "f3m", "f2m", "fta", "ftm", "orb", "drb", "ast", "stl", "blk", "tov", "pf",
              "inside_a", "inside_m", "mid_a", "mid_m", "corner_a", "corner_m", "above_a", "above_m")
FLOW_STATS = ("lead_changes", "ties", "max_lead_home", "max_lead_away", "best_run_home", "best_run_away")
MINUTE_POINTS = 41
POINTS = {"2FGM": 2, "3FGM": 3, "FTM": 1}
PRE_RUNS = 80


def _team_row(side) -> dict[str, float]:
    box = np.asarray(side.box, dtype=float).sum(axis=0)
    z = side.zones
    return {"pts": side.pts, "poss": side.poss, "fga": box[F2A] + box[F3A], "f2a": box[F2A], "f3a": box[F3A], "f3m": box[F3M], "f2m": box[F2M],
            "fta": box[FTA], "ftm": box[FTM], "orb": box[ORB], "drb": box[DRB], "ast": box[AST], "stl": box[STL], "blk": box[BLK],
            "tov": box[TOV], "pf": box[PF], "inside_a": z[0], "mid_a": z[1], "corner_a": z[2], "above_a": z[3],
            "inside_m": z[4], "mid_m": z[5], "corner_m": z[6], "above_m": z[7]}


class Many:
    """The result of n simulated games."""

    def __init__(self, home: TeamModel, away: TeamModel, n: int):
        self.home, self.away, self.n = home, away, n
        self.team = {0: {k: np.zeros(n) for k in TEAM_STATS}, 1: {k: np.zeros(n) for k in TEAM_STATS}}
        self.flow = {k: np.zeros(n) for k in FLOW_STATS}
        self.margins = np.zeros((n, MINUTE_POINTS))
        self.quarters = np.zeros((n, 4, 2))
        self.subs = np.zeros((n, 2))
        self.overtime = np.zeros(n, dtype=bool)
        self.players = {0: np.zeros((n, len(home.players), len(BOX_INDEX))), 1: np.zeros((n, len(away.players), len(BOX_INDEX)))}
        self.box_columns = list(BOX_INDEX)
        self.expected = 0.0
        self.player_parts = {0: np.zeros((n, len(home.players), 5)), 1: np.zeros((n, len(away.players), 5))}
        self.transition = {0: np.zeros(n), 1: np.zeros(n)}

    @property
    def home_pts(self) -> np.ndarray:
        return self.team[0]["pts"]

    @property
    def away_pts(self) -> np.ndarray:
        return self.team[1]["pts"]

    @property
    def home_win(self) -> float:
        return float((self.home_pts > self.away_pts).mean())


def expected_margin(home: TeamModel, away: TeamModel, league: dict, tune: Tuning | None = None, neutral: bool = False,
                    n: int = PRE_RUNS, seed: int = 77_000) -> float:
    """The matchup's expected final margin, from games without any score effect."""
    plain = replace(tune or Tuning(), score_effect=0.0)
    total = 0.0
    for i in range(n):
        g = GameSim(home, away, league, plain, seed=seed + i, neutral=neutral).play()
        total += g.sides[0].pts - g.sides[1].pts
    return total / n


def run_many(home: TeamModel, away: TeamModel, league: dict, tune: Tuning | None = None, n: int = 500, seed: int = 0,
             neutral: bool = False) -> Many:
    m = Many(home, away, n)
    m.expected = expected_margin(home, away, league, tune, neutral)
    columns = list(BOX_INDEX.values())
    for i in range(n):
        g = GameSim(home, away, league, tune, seed=seed + i, neutral=neutral, expected_margin=m.expected).play()
        for s in g.sides:
            row = _team_row(s)
            for k, v in row.items():
                m.team[s.index][k][i] = v
            m.players[s.index][i] = np.asarray(s.box, dtype=float)[:, columns]
            m.subs[i, s.index] = s.subs
            m.player_parts[s.index][i] = s.parts
            m.transition[s.index][i] = s.trans_shots
        m.flow["lead_changes"][i] = g.lead_changes
        m.flow["ties"][i] = g.ties
        m.flow["max_lead_home"][i], m.flow["max_lead_away"][i] = g.max_lead
        m.flow["best_run_home"][i], m.flow["best_run_away"][i] = g.best_run
        m.margins[i] = g.margins[:MINUTE_POINTS]
        m.quarters[i] = g.quarters[:4]
        m.overtime[i] = len(g.quarters) > 4
    return m


# ---- a real game, read the same way ---------------------------------------------------------
def running_score(scoring: pd.DataFrame, home: str) -> tuple[list[tuple[float, int, int]], list[list[int]]]:
    """The score after each basket, and at the end of each quarter.

    Added up from the baskets, because the feed writes a few scores a row early.
    """
    rows, h, a = [], 0, 0
    at_end = [[0, 0], [0, 0], [0, 0], [0, 0]]
    for elapsed, kind, team, period in zip(scoring.elapsed, scoring.type, scoring.team, scoring.period):
        if team == home:
            h += POINTS[kind]
        else:
            a += POINTS[kind]
        rows.append((float(elapsed), h, a))
        for p in range(int(period) - 1, 4):
            at_end[p] = [h, a]
    return rows, at_end


def flow_from_scores(score_rows: list[tuple[float, int, int]]) -> dict:
    """score_rows: (elapsed seconds, home, away) at each change of score, in order."""
    lead_changes = ties = 0
    max_lead = [0, 0]
    best_run = [0, 0]
    run_team, run = -1, 0
    last_leader = -1
    hp, ap = 0, 0
    margins = [0.0]
    minute = 60.0
    for elapsed, h, a in score_rows:
        while elapsed >= minute and len(margins) < MINUTE_POINTS:
            margins.append(float(hp - ap))
            minute += 60.0
        scorer = 0 if h > hp else 1 if a > ap else -1
        pts = (h - hp) + (a - ap)
        hp, ap = h, a
        if scorer < 0:
            continue
        margin = hp - ap
        if margin == 0:
            ties += 1
        else:
            leader = 0 if margin > 0 else 1
            if last_leader in (0, 1) and last_leader != leader:
                lead_changes += 1
            last_leader = leader
            max_lead[leader] = max(max_lead[leader], abs(margin))
        run = run + pts if run_team == scorer else pts
        run_team = scorer
        best_run[scorer] = max(best_run[scorer], run)
    while len(margins) < MINUTE_POINTS:
        margins.append(float(hp - ap))
    return {"lead_changes": lead_changes, "ties": ties, "max_lead_home": max_lead[0], "max_lead_away": max_lead[1],
            "best_run_home": best_run[0], "best_run_away": best_run[1], "margins": margins}


def actual_game(t, season: str, gamecode: int, home: str, away: str) -> dict:
    """A played game's box score, zones and flow, in the shape of one simulated game."""
    ev = t.events[(t.events.season == season) & (t.events.gamecode == gamecode)].sort_values("seq")
    pg = t.player_games[(t.player_games.season == season) & (t.player_games.gamecode == gamecode)]
    sh = t.shots[(t.shots.season == season) & (t.shots.gamecode == gamecode)]
    po = t.possessions[(t.possessions.season == season) & (t.possessions.gamecode == gamecode)]
    st = t.stints[(t.stints.season == season) & (t.stints.gamecode == gamecode)]

    scoring = ev[ev.type.isin(list(POINTS))]
    rows, quarters = running_score(scoring, home)
    flow = flow_from_scores(rows)

    team: dict[int, dict[str, float]] = {}
    players: dict[str, dict[str, float]] = {}
    for side, code in ((0, home), (1, away)):
        p = pg[pg.team == code]
        s = sh[sh.team == code]
        z = s.groupby("zone_group").made.agg(["size", "sum"])

        def zone(name: str) -> tuple[float, float]:
            return (float(z.loc[name, "size"]), float(z.loc[name, "sum"])) if name in z.index else (0.0, 0.0)

        ia, im = zone("inside")
        ma, mm = zone("mid")
        ca, cm = zone("corner3")
        aa, am = zone("above_break3")
        team[side] = {"pts": float(p.pts.sum()), "poss": float((po.offense == code).sum()), "fga": float(p.fg2a.sum() + p.fg3a.sum()),
                      "f2a": float(p.fg2a.sum()), "f3a": float(p.fg3a.sum()), "f3m": float(p.fg3m.sum()), "f2m": float(p.fg2m.sum()),
                      "fta": float(p.fta.sum()), "ftm": float(p.ftm.sum()), "orb": float(p.orb.sum()), "drb": float(p.drb.sum()),
                      "ast": float(p.ast.sum()), "stl": float(p.stl.sum()), "blk": float(p.blk.sum()), "tov": float(p.tov.sum()),
                      "pf": float(p.pf.sum()), "inside_a": ia, "inside_m": im, "mid_a": ma, "mid_m": mm, "corner_a": ca, "corner_m": cm,
                      "above_a": aa, "above_m": am}
        mine = st[st.team == code]
        late_seconds = mine.assign(late=(mine.end.clip(upper=2400) - mine.start.clip(lower=2100)).clip(lower=0)).groupby("player_id").late.sum()
        own_points = s[s.made & ~s.assisted & ~s.is_heave & (s.context != "putback")].groupby("player_id").value.sum()
        for r in p.itertuples():
            players[str(r.player_id)] = {"late": float(late_seconds.get(r.player_id, 0)), "self": float(own_points.get(r.player_id, 0)), "sec": float(r.minutes) * 60, "pts": float(r.pts), "f2m": float(r.fg2m), "f2a": float(r.fg2a),
                                         "f3m": float(r.fg3m), "f3a": float(r.fg3a), "ftm": float(r.ftm), "fta": float(r.fta),
                                         "orb": float(r.orb), "drb": float(r.drb), "ast": float(r.ast), "stl": float(r.stl),
                                         "blk": float(r.blk), "tov": float(r.tov), "pf": float(r.pf)}
    subs = ev[ev.type == "IN"].groupby("team").size()
    return {"team": team, "players": players, "flow": flow, "quarters": quarters,
            "subs": [int(subs.get(home, 0)), int(subs.get(away, 0))], "overtime": bool((ev.period > 4).any())}


def games_table() -> pd.DataFrame:
    from bk.config import TABLES_DIR
    return pd.read_parquet(TABLES_DIR / "games.parquet")
