"""Does shrinkage predict future shooting better than raw percentages?

For every month M of a season, estimate each player's make probability per zone
from all games *before* M, then score the actual shots of month M by log-loss:
  raw     : player's raw zone % before M (league % when no attempts)
  shrunk  : the same with the prior strength used by the ratings
  league  : league zone % (baseline, ignores the player)

    uv run python scripts/backtest.py [SEASON]
"""

import sys

import numpy as np
import pandas as pd

from bk.config import TABLES_DIR
from bk.ratings.metrics import PRIOR_K

K = {"rim": PRIOR_K["rim_pct"], "paint": PRIOR_K["paint_pct"], "mid": PRIOR_K["mid_pct"],
     "corner3": PRIOR_K["corner3_pct"], "above_break3": PRIOR_K["three_pct"]}


def logloss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-3, 1 - 1e-3)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def run(season: str) -> pd.DataFrame:
    s = pd.read_parquet(TABLES_DIR / "shots.parquet")
    s = s[(s.season == season) & s.zone.isin(K)].copy()
    s["month"] = s.date.dt.tz_convert(None).dt.to_period("M")
    rows = []
    for m in sorted(s.month.unique())[1:]:
        past, now = s[s.month < m], s[s.month == m].copy()
        league = past.groupby("zone").made.mean()
        agg = past.groupby(["player_id", "zone"]).made.agg(["sum", "size"])
        now = now.join(agg, on=["player_id", "zone"])
        now[["sum", "size"]] = now[["sum", "size"]].fillna(0)
        p0 = now.zone.map(league)
        k = now.zone.map(K)
        preds = {
            "league": p0,
            "raw": np.where(now["size"] > 0, now["sum"] / now["size"].clip(lower=1), p0),
            "shrunk": (now["sum"] + k * p0) / (now["size"] + k),
        }
        y = now.made.to_numpy(dtype=float)
        rows.append({"month": str(m), "shots": len(now), **{n: logloss(y, np.asarray(p, dtype=float)) for n, p in preds.items()}})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    season = sys.argv[1] if len(sys.argv) > 1 else "E2025"
    df = run(season)
    print(df.round(4).to_string(index=False))
    w = df.shots / df.shots.sum()
    print("\nweighted log-loss:", {c: round(float((df[c] * w).sum()), 4) for c in ["league", "raw", "shrunk"]})
