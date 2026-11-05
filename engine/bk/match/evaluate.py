"""How simulated games compare with the real ones they stand for.

A single simulated game will never replay the real one event by event: most of what happens in a
possession is chance. The fair question is whether what really happened is a plausible draw from
what the model expected, and whether that holds across many games: an 80% range should hold the
real value about 80% of the time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from bk.match.model import TeamModel
from bk.match.runner import Many, actual_game, run_many

TEAM_CHECKS = ("pts", "poss", "fga", "f3a", "fta", "tov", "orb", "drb", "ast", "stl", "blk", "pf", "inside_a", "mid_a")
PLAYER_CHECKS = ("sec", "pts", "orb", "drb", "ast", "tov", "f3a", "fta")
FLOW_CHECKS = ("lead_changes", "ties", "max_lead_home", "max_lead_away", "best_run_home", "best_run_away")


def clip(p: float, n: int) -> float:
    low = 1 / (n + 1)
    return min(max(p, low), 1 - low)


def percentile(values: np.ndarray, x: float) -> float:
    """Where a real value falls in the simulated range. Ties share the middle."""
    return float((np.mean(values < x) + np.mean(values <= x)) / 2)


def inside_80(values: np.ndarray, x: float) -> bool:
    lo, hi = np.quantile(values, [0.1, 0.9])
    return bool(lo <= x <= hi)


@dataclass
class GameScore:
    season: str
    gamecode: int
    home: str
    away: str
    actual_home: float
    actual_away: float
    p_home: float
    sim_home: float
    sim_away: float
    margin_in_80: bool
    total_in_80: bool
    team_in_80: dict[str, list[bool]] = field(default_factory=dict)
    team_error: dict[str, list[float]] = field(default_factory=dict)
    team_sim: dict[str, list[float]] = field(default_factory=dict)
    team_actual: dict[str, list[float]] = field(default_factory=dict)
    player_rows: list[dict] = field(default_factory=list)
    flow_in_80: dict[str, bool] = field(default_factory=dict)
    flow_sim: dict[str, float] = field(default_factory=dict)
    flow_actual: dict[str, float] = field(default_factory=dict)
    margin_curve_in_80: float = 0.0
    margin_sd: float = 0.0
    total_sd: float = 0.0
    timeouts_sim: float = 0.0
    subs_sim: list[float] = field(default_factory=list)
    subs_actual: list[int] = field(default_factory=list)


def score_game(m: Many, actual: dict, baseline: dict | None = None, season: str = "", gamecode: int = 0) -> GameScore:
    h, a = actual["team"][0]["pts"], actual["team"][1]["pts"]
    margin = m.home_pts - m.away_pts
    total = m.home_pts + m.away_pts
    gs = GameScore(season, gamecode, m.home.code, m.away.code, h, a, clip(m.home_win, m.n), float(m.home_pts.mean()), float(m.away_pts.mean()),
                   inside_80(margin, h - a), inside_80(total, h + a))
    for k in TEAM_CHECKS:
        gs.team_in_80[k] = [inside_80(m.team[s][k], actual["team"][s][k]) for s in (0, 1)]
        gs.team_sim[k] = [float(m.team[s][k].mean()) for s in (0, 1)]
        gs.team_actual[k] = [actual["team"][s][k] for s in (0, 1)]
        gs.team_error[k] = [abs(gs.team_sim[k][s] - gs.team_actual[k][s]) for s in (0, 1)]
    columns = m.box_columns
    for side, team in ((0, m.home), (1, m.away)):
        for j, p in enumerate(team.players):
            real = actual["players"].get(p.player_id)
            if real is None:
                continue
            row: dict = {"player_id": p.player_id, "name": p.name, "team": team.code, "starter": p.starter}
            for k in PLAYER_CHECKS:
                v = m.players[side][:, j, columns.index(k)]
                row[f"{k}_sim"] = float(v.mean())
                row[f"{k}_real"] = real[k]
                row[f"{k}_in80"] = inside_80(v, real[k])
            if baseline is not None:
                base = baseline.get(p.player_id)
                if base:
                    for k in PLAYER_CHECKS:
                        row[f"{k}_base"] = base.get(k)
            gs.player_rows.append(row)
    for k in FLOW_CHECKS:
        gs.flow_in_80[k] = inside_80(m.flow[k], actual["flow"][k])
        gs.flow_sim[k] = float(m.flow[k].mean())
        gs.flow_actual[k] = float(actual["flow"][k])
    lo, hi = np.quantile(m.margins, [0.1, 0.9], axis=0)
    real = np.array(actual["flow"]["margins"])
    gs.margin_curve_in_80 = float(np.mean((real >= lo) & (real <= hi)))
    gs.margin_sd, gs.total_sd = float(margin.std()), float(total.std())
    gs.subs_sim = [float(m.subs[:, 0].mean()), float(m.subs[:, 1].mean())]
    gs.subs_actual = actual["subs"]
    return gs


def season_averages_before(pg, season: str, date) -> dict[str, dict]:
    """What each player averaged before a game, as the plain benchmark to beat."""
    d = pg[(pg.season == season) & (pg.date < date) & (pg.minutes > 0)]
    if d.empty:
        return {}
    a = d.groupby("player_id").agg(sec=("minutes", lambda v: 60 * v.mean()), pts=("pts", "mean"), orb=("orb", "mean"), drb=("drb", "mean"),
                                   ast=("ast", "mean"), tov=("tov", "mean"), f3a=("fg3a", "mean"), fta=("fta", "mean"))
    return {str(k): {c: float(v) for c, v in row.items()} for k, row in a.to_dict("index").items()}


def summarize(scores: list[GameScore]) -> dict:
    """Every number the accuracy gates look at."""
    if not scores:
        return {}
    y = np.array([s.actual_home > s.actual_away for s in scores], dtype=float)
    p = np.array([s.p_home for s in scores])
    base = float(np.clip(y.mean(), 0.01, 0.99))
    margin = np.array([s.actual_home - s.actual_away for s in scores])
    sim_margin = np.array([s.sim_home - s.sim_away for s in scores])
    total = np.array([s.actual_home + s.actual_away for s in scores])
    sim_total = np.array([s.sim_home + s.sim_away for s in scores])
    out: dict = {
        "games": len(scores),
        "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
        "log_loss_base_rate": float(-np.mean(y * np.log(base) + (1 - y) * np.log(1 - base))),
        "winner_accuracy": float(np.mean((p > 0.5) == (y == 1))),
        "margin_mae": float(np.mean(np.abs(margin - sim_margin))),
        "margin_bias": float(np.mean(sim_margin - margin)),
        "total_mae": float(np.mean(np.abs(total - sim_total))),
        "total_bias": float(np.mean(sim_total - total)),
        "margin_in_80": float(np.mean([s.margin_in_80 for s in scores])),
        "total_in_80": float(np.mean([s.total_in_80 for s in scores])),
        "margin_curve_in_80": float(np.mean([s.margin_curve_in_80 for s in scores])),
        "margin_sd_sim": float(np.mean([s.margin_sd for s in scores])),
        "margin_rmse": float(np.sqrt(np.mean((margin - sim_margin) ** 2))),
        "total_sd_sim": float(np.mean([s.total_sd for s in scores])),
        "total_rmse": float(np.sqrt(np.mean((total - sim_total) ** 2))),
        "subs_sim": float(np.mean([np.mean(s.subs_sim) for s in scores])),
        "subs_real": float(np.mean([np.mean(s.subs_actual) for s in scores])),
        "team": {}, "player": {}, "flow": {},
    }
    for k in TEAM_CHECKS:
        sims = np.array([s.team_sim[k] for s in scores]).ravel()
        real = np.array([s.team_actual[k] for s in scores]).ravel()
        out["team"][k] = {"sim": round(float(sims.mean()), 2), "real": round(float(real.mean()), 2),
                          "in_80": round(float(np.mean([s.team_in_80[k] for s in scores])), 3),
                          "corr": round(float(np.corrcoef(sims, real)[0, 1]), 3) if sims.std() > 0 else 0.0}
    rows = [r for s in scores for r in s.player_rows]
    for k in PLAYER_CHECKS:
        real = np.array([r[f"{k}_real"] for r in rows], dtype=float)
        sims = np.array([r[f"{k}_sim"] for r in rows], dtype=float)
        scale = 60.0 if k == "sec" else 1.0
        with_base = [r for r in rows if r.get(f"{k}_base") is not None]
        entry = {"sim_mean": round(float(sims.mean()) / scale, 2), "real_mean": round(float(real.mean()) / scale, 2),
                 "mae": round(float(np.mean(np.abs(sims - real))) / scale, 3),
                 "in_80": round(float(np.mean([r[f"{k}_in80"] for r in rows])), 3)}
        if with_base:
            b = np.array([r[f"{k}_base"] for r in with_base], dtype=float)
            rr = np.array([r[f"{k}_real"] for r in with_base], dtype=float)
            ss = np.array([r[f"{k}_sim"] for r in with_base], dtype=float)
            entry["mae_sim_same_rows"] = round(float(np.mean(np.abs(ss - rr))) / scale, 3)
            entry["mae_season_average"] = round(float(np.mean(np.abs(b - rr))) / scale, 3)
        out["player"][k] = entry
    for k in FLOW_CHECKS:
        out["flow"][k] = {"sim": round(float(np.mean([s.flow_sim[k] for s in scores])), 2), "real": round(float(np.mean([s.flow_actual[k] for s in scores])), 2),
                          "in_80": round(float(np.mean([s.flow_in_80[k] for s in scores])), 3)}
    return out


def evaluate_game(home: TeamModel, away: TeamModel, league: dict, tune, t, season: str, gamecode: int, date, n: int = 300, seed: int = 0) -> tuple[Many, dict, GameScore]:
    m = run_many(home, away, league, tune, n, seed)
    actual = actual_game(t, season, gamecode, home.code, away.code)
    base = season_averages_before(t.player_games, season, date)
    return m, actual, score_game(m, actual, base, season, gamecode)
