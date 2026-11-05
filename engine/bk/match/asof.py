"""Tables as they stood before a given moment, so a simulated game never sees its own future."""

from __future__ import annotations

import pandas as pd

from bk.ratings.metrics_v2 import Tables


def before(t: Tables, season: str, date) -> Tables:
    """Every earlier season, plus the games of `season` played before `date`."""
    pg = t.player_games
    kept = pg[(pg.season < season) | ((pg.season == season) & (pg.date < pd.Timestamp(date)))]
    games = pd.MultiIndex.from_frame(kept[["season", "gamecode"]].drop_duplicates())

    def cut(df: pd.DataFrame | None) -> pd.DataFrame | None:
        if df is None:
            return None
        return df[pd.MultiIndex.from_frame(df[["season", "gamecode"]]).isin(games)]

    return Tables(cut(t.shots), kept, cut(t.possessions), cut(t.rebounds), cut(t.fouls), cut(t.trips),
                  t.people[t.people.season <= season], cut(t.events), cut(t.stints))
