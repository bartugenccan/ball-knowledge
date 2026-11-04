"""Clutch, game load, consistency and the single-game rating, built side by side with the current ones."""

from __future__ import annotations

import numpy as np
import pandas as pd

from bk.ratings.attributes import Attribute
from bk.ratings.method import REFERENCE_SEASONS
from bk.ratings.metrics import CLUTCH_CLOCK, CLUTCH_MARGIN, CLUTCH_PERIOD, game_score
from bk.ratings.metrics_v2 import Spec, Tables, league_level, months_of, shrink

LONG_STINT_SECONDS = 420
FT_USE = 0.44
OWN_LEVEL_PRIOR = 100.0        # plays: how fast a player's own efficiency replaces the league's
CONSISTENCY_MIN_MINUTES = 10
MAD_TO_SD = 1.4826
MIN_GAMES_FOR_SPREAD_FIT = 4
PER_MINUTES = 30
SHORT_GAME_MINUTES = 10
RATING_CENTER, RATING_SLOPE, RATING_MIN, RATING_MAX = 6.6, 1.1, 3.0, 10.0

PLAY_POINTS = {"2FGM": 2, "2FGA": 0, "3FGM": 3, "3FGA": 0, "TO": 0, "FTM": 1, "FTA": 0}
PLAY_USE = {"2FGM": 1.0, "2FGA": 1.0, "3FGM": 1.0, "3FGA": 1.0, "TO": 1.0, "FTM": FT_USE, "FTA": FT_USE}


def clutch_counts(t: Tables) -> dict[str, tuple[pd.Series, pd.Series]]:
    """Points above the player's own usual efficiency on clutch plays, including turnovers and free throws."""
    e = t.events.sort_values(["season", "gamecode", "seq"])
    g = e.groupby(["season", "gamecode"])
    margin = (g.home_score.shift(1).fillna(0) - g.away_score.shift(1).fillna(0)).abs()
    clutch = (e.period >= CLUTCH_PERIOD) & (e.clock_left <= CLUTCH_CLOCK) & (margin <= CLUTCH_MARGIN)
    plays = e[e.type.isin(PLAY_USE) & (e.player_id != "")].assign(clutch=clutch)
    plays["points"] = plays.type.map(PLAY_POINTS).astype(float)
    plays["use"] = plays.type.map(PLAY_USE).astype(float)
    league = plays.points.sum() / plays.use.sum()
    usual = plays[~plays.clutch].groupby("player_id")[["points", "use"]].sum()
    own = (usual.points + OWN_LEVEL_PRIOR * league) / (usual.use + OWN_LEVEL_PRIOR)
    late = plays[plays.clutch].groupby("player_id")[["points", "use"]].sum()
    expected = own.reindex(late.index).fillna(league) * late.use
    return {"clutch_value": (late.points - expected, late.use), "clutch_points": (late.points, late.use)}


def load_counts(t: Tables) -> dict[str, tuple[pd.Series, pd.Series]]:
    """Minutes per team game, and the share of minutes played in stints of 7+ minutes."""
    pg = t.player_games
    team_games = pg.groupby("team").gamecode.nunique()
    per = pg.groupby(["player_id", "team"]).size().rename("games").reset_index()
    per["team_games"] = per.team.map(team_games)
    available = per.groupby("player_id").team_games.sum().astype(float)
    minutes = pg.groupby("player_id").minutes.sum().astype(float)
    stints = t.stints
    long_minutes = stints[stints.seconds >= LONG_STINT_SECONDS].groupby("player_id").seconds.sum().div(60)
    all_minutes = stints.groupby("player_id").seconds.sum().div(60)
    return {"load_minutes": (minutes, available), "long_stint_share": (long_minutes, all_minutes)}


def spread_table(pg: pd.DataFrame) -> pd.DataFrame:
    """Each player's game-to-game spread around his own level, and that level, per 30 minutes."""
    g = pg.assign(gmsc=game_score(pg))
    g = g[g.minutes >= CONSISTENCY_MIN_MINUTES]
    totals = g.groupby("player_id")[["gmsc", "minutes"]].sum()
    rate = totals.gmsc / totals.minutes
    g["resid"] = g.gmsc - g.player_id.map(rate) * g.minutes
    by_player = g.groupby("player_id").resid
    spread = MAD_TO_SD * (g.resid - by_player.transform("median")).abs().groupby(g.player_id).median()
    return pd.DataFrame({"spread": spread, "level": PER_MINUTES * rate, "n": by_player.size().astype(float)})


def fit_spread_on_level(tables: list[pd.DataFrame]) -> np.ndarray:
    """Expected spread for a player's level and number of games.

    Higher-output players naturally swing more. Few games make the spread look too small, because
    the player's level comes from those same games; the 1/n term removes that.
    """
    d = pd.concat(tables)
    d = d[d.n >= MIN_GAMES_FOR_SPREAD_FIT]
    root = np.sqrt(d.n.to_numpy(float))
    x = np.column_stack([np.ones(len(d)), d.level.to_numpy(float), 1 / d.n.to_numpy(float)])
    return np.linalg.lstsq(x * root[:, None], d.spread.to_numpy(float) * root, rcond=None)[0]


def consistency_counts(pg: pd.DataFrame, coefficients: np.ndarray) -> tuple[pd.Series, pd.Series]:
    """Spread above what a player of this level would show. Lower is steadier."""
    d = spread_table(pg)
    excess = d.spread - (coefficients[0] + coefficients[1] * d.level + coefficients[2] / d.n)
    return excess * d.n, d.n


MENTAL_SPECS: dict[str, Spec] = {
    # no lasting difference between players: reported as this season's numbers, never as a skill
    "clutch_value": Spec("resid", 8000, dispersion=1.7),
    # descriptive numbers about the current role, so the within-season best applies
    "load_minutes": Spec("resid", 8, dispersion=36.0),
    "long_stint_share": Spec("prop", 80, dispersion=8.0),
    # k=60 is the season-ahead best; a small k lets a nine-game sample swing a player from 3 to 17
    "consistency_value": Spec("resid", 60, dispersion=20.0),
}

INFO_ONLY = ("clutch_value",)

MENTAL_ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute("stamina", "Oyun Yükü", "zihinsel", "veri", (("load_minutes", .6, 1), ("long_stint_share", .4, 1)),
              "Takım maçı başına dakika ve dakikaların 7+ dk kesintisiz seride geçen payı; fiziksel dayanıklılık ölçümü değildir"),
    Attribute("consistency", "İstikrar", "zihinsel", "turetilmis", (("consistency_value", 1, -1),),
              "Maçtan maça dalgalanma, aynı üretim seviyesindeki oyunculara göre (düşük dalga iyi)"),
)


def add_mental_metrics(t: Tables, metrics: pd.DataFrame) -> pd.DataFrame:
    """Add load and consistency estimates plus this season's raw clutch numbers to the metric rows."""
    seasons = sorted(metrics.season.unique())
    coefficients = fit_spread_on_level([spread_table(t.window(x).player_games) for x in REFERENCE_SEASONS if x in seasons])
    frames = []
    for season, m in metrics.groupby("season", sort=False):
        w = t.window(season)
        m = m.set_index("player_id").copy()
        found = {**clutch_counts(w), **load_counts(w), "consistency_value": consistency_counts(w.player_games, coefficients)}
        for metric, spec in MENTAL_SPECS.items():
            s, n = found[metric]
            theta, total, se = shrink(s, n, spec, league_level(s, n), index=m.index)
            m[metric], m[f"n_{metric}"], m[f"se_{metric}"] = theta, total, se
        m["clutch_points"] = found["clutch_points"][0].reindex(m.index).fillna(0.0)
        m["clutch_use"] = found["clutch_points"][1].reindex(m.index).fillna(0.0)
        frames.append(m.reset_index())
    return pd.concat(frames, ignore_index=True)


def add_mental_months(t: Tables, metrics: pd.DataFrame) -> pd.DataFrame:
    """Monthly game load, pulled toward the level before that month. Consistency stays neutral:
    a month is far too short to judge it."""
    empty = pd.Series(dtype=float)
    frames = []
    for season, per_season in metrics.groupby("season", sort=False):
        w = t.window(season)
        whole = load_counts(w)
        month_map = months_of(w.player_games)
        before: set = set()
        for month in sorted(month_map.unique()):
            games = set(month_map.index[month_map == month])
            m = per_season[per_season.month == str(month)].set_index("player_id").copy()
            now = load_counts(t.window(season, games))
            earlier = load_counts(t.window(season, before)) if before else None
            for metric in ("load_minutes", "long_stint_share"):
                spec = MENTAL_SPECS[metric]
                level = league_level(*whole[metric])
                s0, n0 = earlier[metric] if earlier else (empty, empty)
                pre, _, _ = shrink(s0, n0, spec, level, index=m.index)
                s, n = now[metric]
                theta, total, se = shrink(s, n, spec, level, pre - level, index=m.index)
                m[metric], m[f"n_{metric}"], m[f"se_{metric}"] = theta, total, se
            spec = MENTAL_SPECS["consistency_value"]
            m["consistency_value"] = 0.0
            m["n_consistency_value"] = m.games.astype(float)
            m["se_consistency_value"] = np.sqrt(spec.dispersion / spec.k)
            frames.append(m.reset_index())
            before |= games
    return pd.concat(frames, ignore_index=True)


# ---- single-game rating ---------------------------------------------------------------------

def game_rating_v2(pg: pd.DataFrame, plus_minus_weight: float = 0.0) -> pd.DataFrame:
    """1-10 rating per game, spread set separately for each season.

    z compares the game with what those minutes usually yield. plus_minus_weight mixes in the
    same measure for the on-court point margin.
    """
    g = pg.copy()
    g["gmsc"] = game_score(g)

    def standardize(values: pd.Series) -> pd.Series:
        out = pd.Series(0.0, index=g.index)
        for _, idx in g.groupby("season").groups.items():
            part = g.loc[idx]
            resid = values.loc[idx] - values.loc[idx].sum() / part.minutes.sum() * part.minutes
            out.loc[idx] = resid / (resid[part.minutes >= SHORT_GAME_MINUTES].std() or 1.0)
        return out

    z = standardize(g.gmsc)
    if plus_minus_weight > 0:
        z = (1 - plus_minus_weight) * z + plus_minus_weight * standardize(g.plus_minus.astype(float))
    g["game_z"] = z
    g["game_rating"] = np.clip(RATING_CENTER + RATING_SLOPE * z, RATING_MIN, RATING_MAX).round(1)
    g["short_game"] = g.minutes < SHORT_GAME_MINUTES
    return g


def next_game_power(g: pd.DataFrame, column: str = "game_z") -> float:
    """Correlation of a game's value with the player's production in his next game (10+ minutes both)."""
    d = g[~g.short_game].sort_values(["season", "player_id", "date"]).copy()
    by = d.groupby(["season", "player_id"])
    d["next_gmsc"] = by.gmsc.shift(-1)
    d["next_minutes"] = by.minutes.shift(-1)
    d["total_gmsc"] = by.gmsc.transform("sum")
    d["total_minutes"] = by.minutes.transform("sum")
    d = d.dropna(subset=["next_gmsc"])
    # the player's level without these two games: including them would force a negative relation
    rest = d.total_minutes - d.minutes - d.next_minutes
    d = d[rest > 0]
    own = (d.total_gmsc - d.gmsc - d.next_gmsc) / (d.total_minutes - d.minutes - d.next_minutes)
    target = d.next_gmsc - own * d.next_minutes
    return float(d[column].corr(target))
