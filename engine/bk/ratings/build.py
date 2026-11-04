"""Compute season, monthly and per-game ratings from the built tables.

    uv run python -m bk.ratings.build
Writes data/tables/ratings_season.parquet, ratings_month.parquet, player_metrics.parquet and
game_ratings.parquet. Every formula and parameter choice is documented in data/audit/.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bk.config import TABLES_DIR
from bk.ratings.catalog import PRIOR_K, RATING_ATTRIBUTES
from bk.ratings.defense import add_defense_metrics, add_defense_months, on_off_card, possession_table
from bk.ratings.mental import add_mental_metrics, add_mental_months, game_rating_v2
from bk.ratings.method import fixed_reference, score_fixed
from bk.ratings.metrics import WindowData, league_priors
from bk.ratings.metrics_v2 import Tables, load_tables, month_metrics, season_metrics

META_COLS = ["player", "team", "games", "minutes", "mpg"]
FLAG_COLS = ["three_non_shooter", "mid_non_shooter"]
QUALIFIED_MINUTES_SHARE = 0.15  # of the season's largest minute load, for default player lists
SIM_PCT_RANGE = (0.05, 0.95)


def confidence(m: pd.DataFrame) -> pd.DataFrame:
    """Share of each estimate carried by the player's own data, weakest component."""
    out = pd.DataFrame(index=m.index)
    for a in RATING_ATTRIBUTES:
        shares = []
        for metric, _, _ in a.components:
            n = m[f"n_{metric}"].astype(float).fillna(0)
            k = PRIOR_K[metric]
            shares.append(n / (n + k))
        out[f"{a.key}_conf"] = np.round(np.minimum.reduce(shares), 2)
    return out


def add_simulator_shooting(t: Tables, m: pd.DataFrame) -> pd.DataFrame:
    """Half-court make rates for the simulator: the league's rate plus the player's estimated edge.

    The rim/paint boundary is not comparable across arenas, so both zones share one inside edge.
    """
    frames = []
    for season, g in m.groupby("season", sort=False):
        w = t.window(season)
        p = league_priors(WindowData(w.shots, w.player_games, w.possessions))
        g = g.copy()
        low, high = SIM_PCT_RANGE
        for column, level, edge in (("hc_rim_pct", p["hc_rim"], "rel_inside_adj"), ("hc_paint_pct", p["hc_paint"], "rel_inside_adj"),
                                    ("hc_mid_pct", p["hc_mid"], "rel_mid_pct"), ("hc_corner3_pct", p["hc_corner3"], "rel_corner3_pct"),
                                    ("hc_three_pct", p["hc_three"], "rel_three_pct")):
            g[column] = (level + g[edge]).clip(low, high)
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


def season_table(t: Tables) -> pd.DataFrame:
    m = add_mental_metrics(t, add_defense_metrics(t, season_metrics(t)))
    m = add_simulator_shooting(t, m)
    poss = pd.concat([possession_table(t.window(x)) for x in sorted(m.season.unique())], ignore_index=True)
    return m.merge(on_off_card(t, poss), on=["season", "player_id"], how="left")


def score_rows(m: pd.DataFrame, reference: pd.DataFrame, prior_k: dict[str, float]) -> pd.DataFrame:
    frames = []
    for season, g in m.groupby("season", sort=False):
        g = g.set_index("player_id")
        scored = score_fixed(g, reference, RATING_ATTRIBUTES, prior_k).join(confidence(g))
        frames.append(scored.reset_index().assign(season=season))
    return pd.concat(frames, ignore_index=True)


def build(t: Tables | None = None) -> dict[str, pd.DataFrame]:
    t = t or load_tables()
    metrics = season_table(t)
    reference = fixed_reference(metrics)

    season = metrics[["season", "player_id"] + META_COLS + FLAG_COLS].merge(
        score_rows(metrics, reference, PRIOR_K), on=["season", "player_id"])
    season["qualified"] = season.minutes >= QUALIFIED_MINUTES_SHARE * season.groupby("season").minutes.transform("max")

    months = add_mental_months(t, add_defense_months(t, month_metrics(t)))
    flags = metrics[["season", "player_id"] + FLAG_COLS]
    # a month rating is a form reading built on the earlier level, so small samples are expected
    month_scores = pd.concat([score_rows(g, reference, {}).assign(month=month) for month, g in months.groupby("month", sort=False)],
                             ignore_index=True)
    month = months[["season", "month", "player_id"] + META_COLS].merge(month_scores, on=["season", "month", "player_id"]).merge(
        flags, on=["season", "player_id"], how="left")

    out = {"ratings_season": season, "ratings_month": month, "player_metrics": metrics,
           "game_ratings": game_rating_v2(t.player_games)}
    for name, df in out.items():
        df.to_parquet(TABLES_DIR / f"{name}.parquet", index=False)
    return out


if __name__ == "__main__":
    res = build()
    for name, df in res.items():
        print(f"{name:16s} {len(df):>7,} rows")
    s = res["ratings_season"]
    keys = [a.key for a in RATING_ATTRIBUTES]
    latest = s[(s.season == s.season.max()) & s.qualified]
    print("\nrating distribution (latest season, qualified):")
    print(latest[keys].describe().loc[["mean", "std", "min", "max"]].round(1).T.to_string())
