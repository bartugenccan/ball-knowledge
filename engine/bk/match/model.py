"""Who plays and how, as known before a game.

Players use the same shrunk estimates behind their 1-20 ratings, not the ratings themselves: the
ratings are rank-based, which overstates differences on noisy attributes. The 1-20 numbers are kept
on each player so the story can quote them.

Teams add what player numbers cannot carry: tempo, transition, the shots a defense gives up and a
small residual for team-wide shot making, all shrunk by how little of it survives from one half of
a season to the other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from bk.config import TABLES_DIR
from bk.match.asof import before
from bk.match.calibrate import CALIBRATION_FILE, MINUTES, logit
from bk.ratings.build import score_rows, season_table
from bk.ratings.catalog import PRIOR_K, RATING_ATTRIBUTES
from bk.ratings.method import fixed_reference
from bk.ratings.metrics_v2 import Tables, display_value

ZONES = ("inside", "mid", "corner3", "above_break3")
RATING_KEYS = [a.key for a in RATING_ATTRIBUTES]

# Prior strength for team tendencies, in trials. Set by judgment from how stable each tendency was
# between the first ten games and the rest of E2025, then checked as a whole on the E2025 games.
# They were not fitted one at a time.
K_PACE = 250.0
K_TRANSITION = 300.0
K_ZONE = 500.0
K_FORCED_TO = 700.0
K_DEF_FOUL = 800.0
K_NET = 300.0
K_ORB = 400.0
K_CLOSER_GAMES = 2.0
CLOSE_GAME_MARGIN = 10
RECENT_GAMES = 3
K_OFF_MAKE = {"inside": 900.0, "mid": 1200.0, "corner3": 3000.0, "above_break3": 2500.0}
K_DEF_MAKE = {"inside": 900.0, "mid": 1500.0, "corner3": 4000.0, "above_break3": 3000.0}
PAST_SEASON_WEIGHT = 0.25   # coaches and systems carry over a little; rosters change a lot

K_MINUTES_GAMES = 3.0
K_CURVE_GAMES = 4.0
DEFAULT_BENCH_MINUTES = 6.0
MIN_STARTER_MINUTES = 20.0
MAX_MINUTES = 38.0
TEAM_MINUTES = 200.0
K_CORNER = 40.0
K_SELF = 30.0
COORDS_PER_ZONE = 24
OPENING_MINUTES = (0, 1, 2, 3)


@dataclass
class PlayerModel:
    player_id: str
    name: str
    position: str
    starter: bool
    ft: float
    make: dict[str, float]              # half-court make logit per zone
    rate: dict[str, float]              # field-goal attempts per 100 own possessions
    corner_share: float
    self_share: float                   # how far below the league his makes are assisted (0 = league)
    tov: float
    trip: float
    fd: float
    foul: float
    stl: float
    blk: float
    orb: float
    drb: float
    ast: float
    rim_effect: float
    three_effect: float
    target: float
    curve: list[float]                  # chance of being on court in each game minute
    stint: float                        # usual stint, minutes
    ratings: dict[str, int] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)  # what the card shows instead of a number
    low_data: tuple[str, ...] = ()                        # attributes the rating has too little evidence for
    games_before: int = 0
    recent_minutes: float | None = None  # his last few games, when there are any
    closer: float = 0.3                  # how much of the last five minutes of close games he plays
    coords: dict[str, list[tuple[float, float]]] = field(default_factory=dict)


@dataclass
class TeamModel:
    code: str
    name: str
    players: list[PlayerModel]
    pace_off: float = 0.0
    pace_def: float = 0.0
    trans_off: float = 0.0              # logit shift
    trans_def: float = 0.0
    zone_def: dict[str, float] = field(default_factory=lambda: {"inside": 1.0, "mid": 1.0, "three": 1.0})
    forced_to: float = 1.0
    def_foul: float = 1.0
    off_make: dict[str, float] = field(default_factory=lambda: dict.fromkeys(ZONES, 0.0))
    def_make: dict[str, float] = field(default_factory=lambda: dict.fromkeys(ZONES, 0.0))
    rim_mean: float = 0.0
    three_mean: float = 0.0
    net_off: float = 0.0                # points per 100 above the league, scored, shrunk
    net_def: float = 0.0                # points per 100 above the league, allowed, shrunk
    own_to: float = 1.0                 # its own turnovers against the league, as a ratio
    own_foul: float = 1.0               # its own trips to the line against the league, as a ratio
    orb_off: float = 0.0                # logit shift on its offensive rebounds
    orb_def: float = 0.0                # logit shift on the offensive rebounds it gives up


def load_league() -> dict:
    return json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))


@dataclass
class Snapshot:
    """Everything known before a moment in a season."""
    season: str
    tables: Tables
    metrics: pd.DataFrame
    ratings: pd.DataFrame
    league: dict
    team_stats: dict[str, dict]
    curves: dict[tuple[str, str], tuple[np.ndarray, int]]
    stints: dict[tuple[str, str], float]
    assist_self: dict[str, float]
    corner: dict[str, float]
    coords: dict[str, dict[str, list[tuple[float, float]]]]
    names: dict[str, str]
    people: pd.DataFrame
    closers: dict[tuple[str, str], tuple[float, int]] = field(default_factory=dict)


def _shrink_rate(hits: float, trials: float, level: float, k: float) -> float:
    return (hits + k * level) / (trials + k)


def team_tendencies(t: Tables, season: str, league: dict) -> dict[str, dict]:
    """Tempo, transition, shot mix allowed, forced turnovers, fouls and shot-making residuals per team."""
    out: dict[str, dict] = {}
    past = f"E{int(season[1:]) - 1}"
    weights = {season: 1.0, past: PAST_SEASON_WEIGHT}
    s = t.shots[t.shots.season.isin(weights) & t.shots.zone_group.isin(ZONES)].copy()
    if s.empty:
        return out
    s["w"] = s.season.map(weights)
    first = s[s.since_orb.isna()]
    hc_first = first[(first.context == "halfcourt") & first.poss_seconds.between(8, 28)]
    pace_level = float(np.average(hc_first.poss_seconds, weights=hc_first.w)) if len(hc_first) else 18.0
    trans_level = float(np.average(first.context == "transition", weights=first.w)) if len(first) else 0.13
    group = s.zone_group.map({"inside": "inside", "mid": "mid", "corner3": "three", "above_break3": "three"})
    zone_level = s.groupby(group).w.sum() / s.w.sum()

    po = t.possessions[t.possessions.season.isin(weights)]
    po_w = po.season.map(weights)
    to = t.events[t.events.season.isin(weights) & (t.events.type == "TO")]
    games = po[["season", "gamecode", "offense", "defense"]].drop_duplicates()
    to_by_game = to.merge(games, left_on=["season", "gamecode", "team"], right_on=["season", "gamecode", "offense"])
    to_w = to_by_game.season.map(weights)
    to_level = float(to_w.sum() / max(po_w.sum(), 1.0))
    ppp_level = float((po.points * po_w).sum() / max(po_w.sum(), 1.0))

    trips = t.trips[t.trips.season.isin(weights) & ~t.trips.kind.isin(("technical", "unsportsmanlike"))]
    trips_by_game = trips.merge(games, left_on=["season", "gamecode", "team"], right_on=["season", "gamecode", "offense"])
    trip_w = trips_by_game.season.map(weights)
    trip_level = float(trip_w.sum() / max(po_w.sum(), 1.0))

    chances = t.rebounds[t.rebounds.season.isin(weights) & t.rebounds.lineup_ok & ~t.rebounds.likely_dead & ~t.rebounds.team_rebound].copy()
    chances["w"] = chances.season.map(weights)
    orb_level = float(((chances.type == "O") * chances.w).sum() / max(chances.w.sum(), 1.0)) if len(chances) else 0.28

    for code in sorted(set(s.team) | set(s.opponent)):
        opp = s[s.opponent == code]
        rec: dict = {}
        hc_off, hc_def = hc_first[hc_first.team == code], hc_first[hc_first.opponent == code]
        n_off, n_def = float(hc_off.w.sum()), float(hc_def.w.sum())
        rec["pace_off"] = float((hc_off.poss_seconds * hc_off.w).sum() - n_off * pace_level) / (n_off + K_PACE)
        rec["pace_def"] = float((hc_def.poss_seconds * hc_def.w).sum() - n_def * pace_level) / (n_def + K_PACE)
        f_off, f_def = first[first.team == code], first[first.opponent == code]
        rec["trans_off"] = logit(_shrink_rate(float(((f_off.context == "transition") * f_off.w).sum()), float(f_off.w.sum()),
                                              trans_level, K_TRANSITION)) - logit(trans_level)
        rec["trans_def"] = logit(_shrink_rate(float(((f_def.context == "transition") * f_def.w).sum()), float(f_def.w.sum()),
                                              trans_level, K_TRANSITION)) - logit(trans_level)
        opp_group = group.loc[opp.index]
        total = float(opp.w.sum())
        rec["zone_def"] = {g: _shrink_rate(float(opp.w[opp_group == g].sum()), total, float(zone_level[g]), K_ZONE) / float(zone_level[g])
                           for g in ("inside", "mid", "three")}
        def_poss = float(po_w[po.defense == code].sum())
        forced = float(to_w[to_by_game.defense == code].sum())
        rec["forced_to"] = _shrink_rate(forced, def_poss, to_level, K_FORCED_TO) / to_level
        fouled = float(trip_w[trips_by_game.defense == code].sum())
        rec["def_foul"] = _shrink_rate(fouled, def_poss, trip_level, K_DEF_FOUL) / trip_level
        off_poss = float(po_w[po.offense == code].sum())
        rec["own_to"] = _shrink_rate(float(to_w[to_by_game.team == code].sum()), off_poss, to_level, K_FORCED_TO) / to_level
        rec["own_foul"] = _shrink_rate(float(trip_w[trips_by_game.team == code].sum()), off_poss, trip_level, K_DEF_FOUL) / trip_level
        for side, col in (("orb_off", "offense"), ("orb_def", "defense")):
            part = chances[chances[col] == code]
            got = float((part.type == "O").astype(float).mul(part.w).sum())
            rec[side] = logit(_shrink_rate(got, float(part.w.sum()), orb_level, K_ORB)) - logit(orb_level)
        rec["net_off"] = 100 * (float((po.points * po_w)[po.offense == code].sum()) - off_poss * ppp_level) / (off_poss + K_NET)
        rec["net_def"] = 100 * (float((po.points * po_w)[po.defense == code].sum()) - def_poss * ppp_level) / (def_poss + K_NET)
        out[code] = rec
    return out


def add_make_residuals(stats: dict[str, dict], t: Tables, metrics: pd.DataFrame, season: str, league: dict) -> None:
    """Team shot making beyond what its shooters and the context would give: on offense and on defense."""
    past = f"E{int(season[1:]) - 1}"
    weights = {season: 1.0, past: PAST_SEASON_WEIGHT}
    s = t.shots[t.shots.season.isin(weights) & t.shots.zone_group.isin(ZONES)].copy()
    if s.empty:
        return
    edges = metrics[["season", "player_id", "rel_inside_adj", "rel_mid_pct", "rel_corner3_pct", "rel_three_pct"]]
    s = s.merge(edges, on=["season", "player_id"], how="left")
    column = {"inside": "rel_inside_adj", "mid": "rel_mid_pct", "corner3": "rel_corner3_pct", "above_break3": "rel_three_pct"}
    level = league["make_level"]
    delta = league["make_delta"]
    expected = np.zeros(len(s))
    for z in ZONES:
        mask = (s.zone_group == z).to_numpy()
        edge = s.loc[mask, column[z]].fillna(0.0).to_numpy()
        base = np.clip(level[z] + edge, 0.05, 0.95)
        x = np.log(base / (1 - base))
        ctx = s.loc[mask, "context"].to_numpy()
        for c in ("transition", "putback"):
            x = x + (ctx == c) * delta[c][z]
        expected[mask] = 1 / (1 + np.exp(-x))
    s["gap"] = (s.made.astype(float) - expected) * s.season.map(weights)
    s["w"] = s.season.map(weights)
    for code, rec in stats.items():
        rec["off_make"], rec["def_make"] = {}, {}
        for z in ZONES:
            for side, col, ks in (("off_make", "team", K_OFF_MAKE), ("def_make", "opponent", K_DEF_MAKE)):
                part = s[(s[col] == code) & (s.zone_group == z)]
                n = float(part.w.sum())
                gap = float(part.gap.sum()) / (n + ks[z])
                # move from percentage points to logits at the league's level for that zone
                rec[side][z] = gap / (level[z] * (1 - level[z]))


def on_court_curves(stints: pd.DataFrame, pg: pd.DataFrame, season: str) -> tuple[dict, dict]:
    """Per player, seconds on court in each game minute this season, plus his usual stint length."""
    s = stints[(stints.season == season) & (stints.start < MINUTES * 60)]
    games = pg[(pg.season == season) & (pg.minutes > 0)].groupby(["team", "player_id"]).size()
    curves: dict[tuple[str, str], tuple[np.ndarray, int]] = {}
    usual: dict[tuple[str, str], float] = {}
    for (team, player), g in s.groupby(["team", "player_id"], sort=False):
        seconds = np.zeros(MINUTES)
        for a, b in zip(g.start.to_numpy(), g.end.to_numpy()):
            for m in range(int(a // 60), int(min(b, MINUTES * 60 - 1) // 60) + 1):
                seconds[m] += max(0.0, min(b, (m + 1) * 60) - max(a, m * 60))
        n = int(games.get((team, player), 0))
        if n:
            curves[(team, player)] = (seconds / (60 * n), n)
            usual[(team, player)] = float(g.seconds.mean() / 60)
    return curves, usual


def closing_minutes(t: Tables, season: str) -> dict[tuple[str, str], tuple[float, int]]:
    """Per player: his share of the last five minutes of games still close then, and how many such games."""
    ev = t.events[(t.events.season == season) & t.events.type.isin(["2FGM", "3FGM", "FTM"]) & (t.events.elapsed <= 2100)]
    if ev.empty:
        return {}
    last = ev.sort_values("seq").groupby("gamecode").tail(1)
    close = set(last.gamecode[(last.home_score - last.away_score).abs() <= CLOSE_GAME_MARGIN])
    st = t.stints[(t.stints.season == season) & t.stints.gamecode.isin(close)]
    late = (st.end.clip(upper=2400) - st.start.clip(lower=2100)).clip(lower=0)
    seconds = st.assign(late=late).groupby(["team", "player_id"]).late.sum()
    pg = t.player_games[(t.player_games.season == season) & t.player_games.gamecode.isin(close) & (t.player_games.minutes > 0)]
    games = pg.groupby(["team", "player_id"]).gamecode.nunique()
    return {key: (float(seconds.get(key, 0.0)) / (300.0 * n), int(n)) for key, n in games.items()}


def snapshot(t: Tables, season: str, date=None) -> Snapshot:
    """Build everything once for a moment in time. date=None means all games played so far."""
    cut = before(t, season, date) if date is not None else t
    # in the first round of a season there is nothing from it yet, and earlier seasons stand in
    if cut.player_games.empty:
        raise ValueError(f"no games at all before {date}")
    league = load_league()
    metrics = season_table(cut)
    reference = fixed_reference(metrics)
    ratings = score_rows(metrics, reference, PRIOR_K)
    stats = team_tendencies(cut, season, league)
    add_make_residuals(stats, cut, metrics, season, league)
    curves, stints_ = on_court_curves(cut.stints, cut.player_games, season)
    closers = closing_minutes(cut, season)

    past = f"E{int(season[1:]) - 1}"
    recent = cut.shots[cut.shots.season.isin((season, past)) & cut.shots.zone_group.isin(ZONES)]

    threes = recent[recent.zone_group.isin(("corner3", "above_break3"))]
    corner_level = float((threes.zone_group == "corner3").mean()) if len(threes) else 0.13
    by = threes.groupby("player_id").zone_group
    corner = {p: (float((g == "corner3").sum()) + K_CORNER * corner_level) / (len(g) + K_CORNER) for p, g in by}

    made = recent[recent.made]
    assist_level = float(made.assisted.mean()) if len(made) else 0.6
    assist_self = {p: (float(g.sum()) + K_SELF * assist_level) / (len(g) + K_SELF) - assist_level
                   for p, g in made.groupby("player_id").assisted}

    coords: dict[str, dict[str, list[tuple[float, float]]]] = {}
    good = recent[recent.coord_valid] if "coord_valid" in recent else recent
    for (player, zone), g in good.groupby(["player_id", "zone_group"], sort=False):
        pts = g.tail(COORDS_PER_ZONE)
        coords.setdefault(player, {})[zone] = [(round(float(a), 0), round(float(b), 0)) for a, b in zip(pts.x, pts.y)]

    names: dict[str, str] = {}
    gm = pd.read_parquet(TABLES_DIR / "games.parquet", columns=["season", "home", "away", "home_name", "away_name"])
    gm = gm[gm.season <= season]
    for h, n in zip(gm.home, gm.home_name):
        names[h] = n
    for a, n in zip(gm.away, gm.away_name):
        names[a] = n
    return Snapshot(season, cut, metrics, ratings, league, stats, curves, stints_, assist_self, corner, coords, names,
                    t.people[t.people.season <= season], closers)


def _player_row(snap: Snapshot, pid: str) -> pd.Series | None:
    m = snap.metrics[snap.metrics.player_id == pid]
    if m.empty:
        return None
    same = m[m.season == snap.season]
    return same.iloc[-1] if len(same) else m.sort_values("season").iloc[-1]


def _rating_row(snap: Snapshot, pid: str) -> pd.Series | None:
    r = snap.ratings[snap.ratings.player_id == pid]
    if r.empty:
        return None
    same = r[r.season == snap.season]
    return same.iloc[-1] if len(same) else r.sort_values("season").iloc[-1]


def _average_row(snap: Snapshot) -> pd.Series:
    m = snap.metrics[(snap.metrics.season == snap.season) & (snap.metrics.minutes > 50)]
    if m.empty:
        m = snap.metrics
    return m.mean(numeric_only=True)


def _curve(snap: Snapshot, team: str, pid: str, target: float, starter: bool) -> list[float]:
    template = np.array(snap.league["rotation"]["starter" if starter else "bench"], dtype=float)
    own = snap.curves.get((team, pid))
    if own is None:
        q = template.copy()
    else:
        q = (own[1] * own[0] + K_CURVE_GAMES * template) / (own[1] + K_CURVE_GAMES)
    for _ in range(4):
        total = q.sum()
        if total <= 0:
            break
        q = np.minimum(q * target / total, 0.97)
    # whoever starts tonight opens both halves, whatever he did in earlier games
    for minute in (*OPENING_MINUTES, *(MINUTES // 2 + m for m in OPENING_MINUTES)):
        q[minute] = max(q[minute], 0.9) if starter else min(q[minute], 0.08)
    return [round(float(x), 4) for x in q]


def _position(snap: Snapshot, pid: str) -> str:
    p = snap.people[snap.people.player_id == pid]
    if p.empty:
        return "Forward"
    pos = p.sort_values("season").iloc[-1].position
    return pos if isinstance(pos, str) and pos else "Forward"


def build_player(snap: Snapshot, team: str, pid: str, name: str, starter: bool) -> PlayerModel:
    row = _player_row(snap, pid)
    missing = row is None
    if missing:
        row = _average_row(snap)
    level = snap.league["make_level"]
    edges = {"inside": "rel_inside_adj", "mid": "rel_mid_pct", "corner3": "rel_corner3_pct", "above_break3": "rel_three_pct"}
    make = {}
    for z, col in edges.items():
        edge = 0.0 if missing or pd.isna(row.get(col)) else float(row[col])
        make[z] = logit(float(np.clip(level[z] + edge, 0.05, 0.95)))

    def num(col: str, fallback: float = 0.0) -> float:
        v = row.get(col)
        return fallback if v is None or pd.isna(v) else float(v)

    # per action, as in the hidden ball-care rating: a busy ball handler should not lose it less often for being busy
    usage = num("usage_rate", 20.0)
    tov = usage * num("tov_share", 0.14)

    pg = snap.tables.player_games
    # games he dressed for and did not play count: that is how a coach's depth shows
    now = pg[(pg.season == snap.season) & (pg.player_id == pid) & (pg.team == team)]
    past = f"E{int(snap.season[1:]) - 1}"
    last = pg[(pg.season == past) & (pg.player_id == pid) & (pg.minutes > 0)]
    prior_minutes = float(last.minutes.mean()) if len(last) >= 5 else DEFAULT_BENCH_MINUTES
    n = len(now)
    target = (float(now.minutes.sum()) + K_MINUTES_GAMES * prior_minutes) / (n + K_MINUTES_GAMES)
    if starter:
        target = max(target, MIN_STARTER_MINUTES)

    played = now[now.minutes > 0].sort_values("date")
    recent = float(played.minutes.tail(RECENT_GAMES).mean()) if len(played) else None

    rating = _rating_row(snap, pid)
    ratings: dict[str, int] = {}
    labels: dict[str, str] = {}
    low_data: tuple[str, ...] = ()
    if rating is not None:
        ratings = {k: int(rating[k]) for k in (*RATING_KEYS, "ball_care") if k in rating and not pd.isna(rating[k])}
        low_data = tuple(k for k in RATING_KEYS if bool(rating.get(f"{k}_low_data", False)))
        non_shooter = bool(row.get("three_non_shooter", False)) if not missing else False
        non_mid = bool(row.get("mid_non_shooter", False)) if not missing else False
        for k in RATING_KEYS:
            if k in ratings:
                shown = display_value(k, ratings[k], non_shooter, n, non_mid)
                if shown != str(ratings[k]):
                    labels[k] = shown

    usual_share = min(target / MINUTES, 0.9)
    share, close_games = snap.closers.get((team, pid), (usual_share, 0))
    closer = (close_games * share + K_CLOSER_GAMES * usual_share) / (close_games + K_CLOSER_GAMES)

    return PlayerModel(
        closer=closer, player_id=pid, name=name, position=_position(snap, pid), starter=starter, ft=num("ft_pct", 0.78),
        make=make, rate={"inside": num("inside_rate", 8.0), "mid": num("mid_rate", 2.0), "three": num("three_rate", 7.0)},
        corner_share=snap.corner.get(pid, 0.13), self_share=snap.assist_self.get(pid, 0.0),
        tov=tov, trip=num("trip_rate", 3.0), fd=num("fd_rate", 6.0), foul=num("foul_rate", 6.0), stl=num("stl_rate", 1.5),
        blk=num("blk_share", 0.01), orb=num("orb_share", 0.05), drb=num("drb_share", 0.13), ast=num("ast_share", 0.1),
        rim_effect=num("rim_effect"), three_effect=num("three_att_effect"), target=target, curve=[], stint=snap.stints.get((team, pid), 4.5),
        ratings=ratings, labels=labels, low_data=low_data, games_before=n, coords=snap.coords.get(pid, {}),
        recent_minutes=recent,
    )


def build_team(snap: Snapshot, code: str, roster: list[tuple[str, str, bool]]) -> TeamModel:
    """roster holds (player_id, name, starter) for the players available in this game."""
    players = [build_player(snap, code, pid, name, starter) for pid, name, starter in roster]
    total = sum(p.target for p in players) or 1.0
    scale = TEAM_MINUTES / total
    for _ in range(4):
        for p in players:
            p.target = min(MAX_MINUTES, p.target * scale)
        total = sum(p.target for p in players) or 1.0
        scale = TEAM_MINUTES / total
    for p in players:
        p.curve = _curve(snap, code, p.player_id, p.target, p.starter)
    weights = np.array([p.target for p in players]) / max(sum(p.target for p in players), 1e-9)
    team = TeamModel(code, snap.names.get(code, code), players,
                     rim_mean=5 * float(np.dot(weights, [p.rim_effect for p in players])),
                     three_mean=5 * float(np.dot(weights, [p.three_effect for p in players])))
    rec = snap.team_stats.get(code)
    if rec:
        team.pace_off, team.pace_def = rec["pace_off"], rec["pace_def"]
        team.trans_off, team.trans_def = rec["trans_off"], rec["trans_def"]
        team.zone_def, team.forced_to, team.def_foul = rec["zone_def"], rec["forced_to"], rec["def_foul"]
        team.net_off, team.net_def = rec["net_off"], rec["net_def"]
        team.own_to, team.own_foul = rec["own_to"], rec["own_foul"]
        team.orb_off, team.orb_def = rec["orb_off"], rec["orb_def"]
        team.off_make = rec.get("off_make", team.off_make)
        team.def_make = rec.get("def_make", team.def_make)
    return team


def actual_roster(pg: pd.DataFrame, season: str, gamecode: int, team: str) -> list[tuple[str, str, bool]]:
    """Who was in the box score of a played game. The starters and the available squad are known at tip-off."""
    g = pg[(pg.season == season) & (pg.gamecode == gamecode) & (pg.team == team)]
    return [(str(r.player_id), str(r.player), bool(r.starter)) for r in g.itertuples()]


def likely_roster(snap: Snapshot, team: str, games: int = 6, size: int = 12) -> list[tuple[str, str, bool]]:
    """The squad to expect next. Each game counts half as much as the one after it, so a player who has
    just dropped out fades fast. No injury news goes in: a player out since yesterday still shows up."""
    pg = snap.tables.player_games
    g = pg[(pg.season == snap.season) & (pg.team == team)]
    last = sorted(g.gamecode.unique(), key=lambda c: g[g.gamecode == c].date.iloc[0])[-games:]
    weight = {code: 0.5 ** (len(last) - 1 - i) for i, code in enumerate(last)}
    recent = g[g.gamecode.isin(last)]
    recent = recent.assign(w=recent.gamecode.map(weight))
    recent = recent.assign(w_minutes=recent.minutes * recent.w, w_starts=recent.starter.astype(float) * recent.w)
    agg = recent.groupby("player_id").agg(name=("player", "last"), minutes=("w_minutes", "sum"), starts=("w_starts", "sum"))
    agg = agg[agg.minutes > 0].sort_values("minutes", ascending=False).head(size)
    starters = set(agg.sort_values(["starts", "minutes"], ascending=False).head(5).index)
    return [(str(p), str(r["name"]), p in starters) for p, r in agg.iterrows()]
