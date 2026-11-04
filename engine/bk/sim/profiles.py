"""Load simulator Player profiles from the ratings tables.

The simulator uses *half-court* shooting (transition and putbacks removed),
because a called set is a half-court possession. Ratings on the player card
keep using all shots.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from bk.config import TABLES_DIR
from bk.ratings.catalog import RATING_ATTRIBUTES
from bk.sim.engine import Player

# simulator key -> metrics column
PCT_SOURCE = {"rim_pct": "hc_rim_pct", "paint_pct": "hc_paint_pct", "mid_pct": "hc_mid_pct",
              "corner3_pct": "hc_corner3_pct", "three_pct": "hc_three_pct", "ft_pct": "ft_pct"}


@lru_cache(maxsize=1)
def _tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    r = pd.read_parquet(TABLES_DIR / "ratings_season.parquet").set_index(["season", "player_id"])
    m = pd.read_parquet(TABLES_DIR / "player_metrics.parquet").set_index(["season", "player_id"])
    return r, m


def clear_cache() -> None:
    _tables.cache_clear()
    league_average.cache_clear()


def _pct(row: pd.Series) -> dict[str, float]:
    return {k: float(row[c] if c in row else row[k]) for k, c in PCT_SOURCE.items()}


@lru_cache(maxsize=8)
def league_average(season: str) -> Player:
    """Average rotation player of the season: mean shrunk shooting of qualified players, ratings at average."""
    r, m = _tables()
    q = r.loc[season]
    ids = q.index[q["qualified"]]
    mean = m.loc[season].loc[ids].mean(numeric_only=True)
    return Player.average(pct=_pct(mean))


def load_player(season: str, player_id: str) -> Player:
    r, m = _tables()
    key = (season, player_id)
    if key not in r.index:
        raise KeyError(f"no ratings for {player_id} in {season}")
    row, met = r.loc[key], m.loc[key]
    return Player(player_id=player_id, name=str(row["player"]).title(),
                  ratings={a.key: int(row[a.key]) for a in RATING_ATTRIBUTES}, pct=_pct(met))
