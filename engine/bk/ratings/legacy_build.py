"""The first rating method, kept so the audit reports stay reproducible. Nothing in the product reads it.

    uv run python -m bk.ratings.legacy_build
Writes data/tables/ratings_season_v1.parquet, ratings_month_v1, player_metrics_v1, game_ratings_v1
"""

from __future__ import annotations

import pandas as pd

from bk.config import TABLES_DIR
from bk.ratings.attributes import ATTRIBUTES, qualified, score
from bk.ratings.metrics import (WindowData, carry_counts, compute_metrics, game_ratings, league_priors,
                                shooter_expectation)

META_COLS = ["player", "team", "games", "minutes", "mpg", "off_poss", "def_poss"]
CARRY_WEIGHTS = (1.0, 0.5)  # last season, two seasons ago


def load() -> WindowData:
    return WindowData(
        shots=pd.read_parquet(TABLES_DIR / "shots.parquet"),
        player_games=pd.read_parquet(TABLES_DIR / "player_games.parquet"),
        possessions=pd.read_parquet(TABLES_DIR / "possessions.parquet"),
    )


def _slice(d: WindowData, season: str, month: pd.Period | None = None) -> WindowData:
    s = d.shots[d.shots.season == season]
    pg = d.player_games[d.player_games.season == season]
    po = d.possessions[d.possessions.season == season]
    if month is not None:
        games = pg.loc[pg.date.dt.tz_convert(None).dt.to_period("M") == month, "gamecode"].unique()
        s, pg, po = s[s.gamecode.isin(games)], pg[pg.gamecode.isin(games)], po[po.gamecode.isin(games)]
    return WindowData(s, pg, po)


def build(d: WindowData | None = None) -> dict[str, pd.DataFrame]:
    d = d or load()
    season_rows, month_rows, metric_rows = [], [], []
    seasons = sorted(d.player_games.season.unique())
    for i, season in enumerate(seasons):
        sd = _slice(d, season)
        priors = league_priors(sd)
        expected = shooter_expectation(sd.shots, priors)  # season-level shooter skill
        # season view pools earlier seasons' shooting; month view stays a pure form window
        history = [(_slice(d, prev).shots, _slice(d, prev).player_games, w)
                   for prev, w in zip(reversed(seasons[:i]), CARRY_WEIGHTS)]
        m = compute_metrics(sd, priors, expected, carry=carry_counts(history))
        ref = m[qualified(m)]
        r = score(m, ref)
        season_rows.append(m[META_COLS].join(r).assign(season=season, qualified=qualified(m)))
        metric_rows.append(m.assign(season=season))

        months = sd.player_games.date.dt.tz_convert(None).dt.to_period("M").unique()
        for month in sorted(months):
            md = _slice(d, season, month)
            mm = compute_metrics(md, priors, expected.reindex(md.shots.index))
            month_rows.append(mm[META_COLS].join(score(mm, ref)).assign(season=season, month=str(month)))

    out = {
        "ratings_season": pd.concat(season_rows).reset_index(),
        "ratings_month": pd.concat(month_rows).reset_index(),
        "player_metrics": pd.concat(metric_rows).reset_index(),
        "game_ratings": game_ratings(d.player_games),
    }
    for name, df in out.items():
        df.to_parquet(TABLES_DIR / f"{name}_v1.parquet", index=False)
    return out


if __name__ == "__main__":
    res = build()
    s = res["ratings_season"]
    for name, df in res.items():
        print(f"{name:16s} {len(df):>7,} rows")
    keys = [a.key for a in ATTRIBUTES]
    latest = s[(s.season == s.season.max()) & s.qualified]
    print("\nrating distribution (latest season, qualified):")
    print(latest[keys].describe().loc[["mean", "std", "min", "max"]].round(1).T.to_string())
