"""Fit the data-observable simulator parameters on EuroLeague play-by-play.

    uv run python -m bk.sim.calibrate

Fatigue and clutch effects are estimated as logistic-regression slopes with the
shooter's own zone expectation as an offset, so they measure the change in
make probability *relative to that shooter's normal level*.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from bk.config import TABLES_DIR
from bk.ratings.metrics import CLUTCH_CLOCK, CLUTCH_MARGIN, CLUTCH_PERIOD, WindowData, league_priors, shooter_expectation
from bk.sim.params import CALIBRATION_FILE, SimParams

FATIGUE_TAU = 0.02   # prior SD of the per-minute fatigue slope (logit)
CLUTCH_TAU = 0.10    # prior SD of the league clutch shift (logit)


def shooting_fouls(events: pd.DataFrame) -> dict[str, int]:
    """Count free-throw trips (2 or 3 shots) and and-ones from the play-by-play.

    A trip is a run of FT events by one player at one game second. A single FT
    right after the same player's made basket is an and-one; other single FTs
    (technicals) are ignored.
    """
    ev = events.sort_values(["season", "gamecode", "seq"])
    ft = ev[ev.type.isin(["FTM", "FTA"])]
    trips = ft.groupby(["season", "gamecode", "player_id", "elapsed"]).size()
    trips2, trips3 = int((trips == 2).sum()), int((trips == 3).sum())
    made = ev[ev.type.isin(["2FGM", "3FGM"])][["season", "gamecode", "player_id", "elapsed", "type"]]
    singles = trips[trips == 1].reset_index()[["season", "gamecode", "player_id", "elapsed"]]
    and1 = singles.merge(made, on=["season", "gamecode", "player_id", "elapsed"])
    return {"trips2": trips2, "trips3": trips3,
            "and1_2": int((and1.type == "2FGM").sum()), "and1_3": int((and1.type == "3FGM").sum())}


def fit_slope(y: np.ndarray, offset: np.ndarray, x: np.ndarray, iters: int = 30) -> tuple[float, float]:
    """1-D logistic regression with an offset: logit p = offset + b·x. Returns (b, standard error)."""
    b = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(offset + b * x)))
        grad = np.sum((y - p) * x)
        hess = np.sum(p * (1 - p) * x * x)
        if hess <= 0:
            break
        step = grad / hess
        b += step
        if abs(step) < 1e-8:
            break
    p = 1 / (1 + np.exp(-(offset + b * x)))
    se = 1 / math.sqrt(max(np.sum(p * (1 - p) * x * x), 1e-9))
    return float(b), float(se)


def calibrate(free_min: float = 5.0) -> dict:
    shots = pd.read_parquet(TABLES_DIR / "shots.parquet")
    pg = pd.read_parquet(TABLES_DIR / "player_games.parquet")
    po = pd.read_parquet(TABLES_DIR / "possessions.parquet")
    parts = []
    for season in shots.season.unique():
        d = WindowData(shots[shots.season == season], pg[pg.season == season], po[po.season == season])
        s = d.shots.copy()
        s["exp"] = shooter_expectation(s, league_priors(d))
        parts.append(s)
    s = pd.concat(parts)
    y = s.made.to_numpy(dtype=float)
    off = np.log(s.exp.clip(1e-4, 1 - 1e-4) / (1 - s.exp.clip(1e-4, 1 - 1e-4))).to_numpy()

    over = np.maximum(0.0, s.stint_seconds.to_numpy() / 60 - free_min)
    fat, fat_se = fit_slope(y, off, over)
    clutch = ((s.period >= CLUTCH_PERIOD) & (s.clock_left <= CLUTCH_CLOCK)
              & (s.margin_before.abs() <= CLUTCH_MARGIN)).to_numpy(dtype=float)
    cl, cl_se = fit_slope(y, off, clutch)
    # shrink noisy slopes toward zero with a normal prior (tau = plausible effect size)
    fat_post = fat * FATIGUE_TAU**2 / (FATIGUE_TAU**2 + fat_se**2)
    cl_post = cl * CLUTCH_TAU**2 / (CLUTCH_TAU**2 + cl_se**2)

    events = pd.read_parquet(TABLES_DIR / "events.parquet")
    fouls = shooting_fouls(events)
    fga2, fga3 = int((s.value == 2).sum()), int((s.value == 3).sum())
    foul2 = (fouls["trips2"] + fouls["and1_2"]) / (fga2 + fouls["trips2"])
    foul3 = (fouls["trips3"] + fouls["and1_3"]) / (fga3 + fouls["trips3"])
    total_fouls = fouls["trips2"] + fouls["trips3"] + fouls["and1_2"] + fouls["and1_3"]
    and_one_share = (fouls["and1_2"] + fouls["and1_3"]) / max(total_fouls, 1)
    # keep the prior's rim:paint:mid ratio but match the observed 2-pt shooting-foul rate
    prior = SimParams().shooting_foul_rate
    share2 = s[s.value == 2].zone.value_counts(normalize=True)
    prior_mix = sum(prior[z] * share2.get(z, 0) for z in ("rim", "paint", "mid")) or 1.0
    scale2 = foul2 / prior_mix
    foul_rate = {z: round(prior[z] * scale2, 4) for z in ("rim", "paint", "mid")}
    foul_rate.update({"corner3": round(foul3, 4), "above_break3": round(foul3, 4)})

    # reference only: per-action turnover rates stay priors (see SimParams.turnover_rate)
    league_tov = float((events.type == "TO").sum() / max(len(po), 1))  # includes team turnovers

    # offensive rebound rate on missed field goals (player box rebounds only)
    games = pg.groupby(["season", "gamecode", "team"])[["orb", "drb"]].sum()
    opp = games.groupby(level=[0, 1]).transform(lambda x: x[::-1].to_numpy())
    orb_rate = float(games.orb.sum() / (games.orb.sum() + opp.drb.sum()))
    sc = s[s.second_chance]
    second_chance_ppp = float((sc.made * sc.value).sum() / max(pg.orb.sum(), 1))

    result = {
        "fatigue_per_min": round(fat_post, 4), "fatigue_free_min": free_min,
        "clutch_league": round(cl_post, 4), "orb_rate": round(orb_rate, 4),
        "second_chance_ppp": round(max(second_chance_ppp, 0.8), 3),
        "shooting_foul_rate": foul_rate, "and_one_share": round(and_one_share, 3),
    }
    report = {**result, "fatigue_raw": round(fat, 4), "fatigue_se": round(fat_se, 4),
              "clutch_raw": round(cl, 4), "clutch_se": round(cl_se, 4),
              "league_tov_per_poss": round(league_tov, 4), "foul_rate_2pt": round(foul2, 4),
              "foul_rate_3pt": round(foul3, 4), "shots": int(len(s)), "clutch_shots": int(clutch.sum()),
              "late_stint_shots": int((over > 0).sum()), **{k: int(v) for k, v in fouls.items()}}
    CALIBRATION_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    for k, v in calibrate().items():
        print(f"{k:20s} {v}")
