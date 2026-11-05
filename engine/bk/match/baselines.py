"""Plain benchmarks a simulated game has to beat, each using only what was known before the game."""

from __future__ import annotations

import numpy as np
import pandas as pd

NET_PRIOR_POSSESSIONS = 300.0
NET_CARRY = 0.5     # how much of last season's net rating a team starts from


def _net_of(po: pd.DataFrame) -> dict[str, tuple[float, float]]:
    """Per team: net points per 100 possessions and how many possessions it rests on."""
    if po.empty:
        return {}
    off = po.groupby("offense").points.agg(["sum", "size"])
    dfn = po.groupby("defense").points.agg(["sum", "size"])
    return {c: (100 * (off.loc[c, "sum"] / off.loc[c, "size"] - dfn.loc[c, "sum"] / dfn.loc[c, "size"]), float(off.loc[c, "size"]))
            for c in off.index if c in dfn.index}


class NetRatings:
    """Team net rating before any date: this season's games, starting from part of last season's level."""

    def __init__(self, possessions: pd.DataFrame, games: pd.DataFrame):
        self.po, self.games = possessions, games
        self.finals = {s: _net_of(possessions[possessions.season == s]) for s in possessions.season.unique()}

    def before(self, season: str, date) -> dict[str, float]:
        played = self.games[(self.games.season == season) & (self.games.date < date)].gamecode
        current = _net_of(self.po[(self.po.season == season) & self.po.gamecode.isin(played)])
        last = self.finals.get(f"E{int(season[1:]) - 1}", {})
        out = {}
        for team in set(current) | set(last):
            raw, n = current.get(team, (0.0, 0.0))
            prior = NET_CARRY * last.get(team, (0.0, 0.0))[0]
            out[team] = (n * raw + NET_PRIOR_POSSESSIONS * prior) / (n + NET_PRIOR_POSSESSIONS)
        return out


def fit_logistic(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Home edge and slope for P(home wins) from the gap in net rating."""
    home, slope = 0.5, 0.05
    for _ in range(40):
        p = 1 / (1 + np.exp(-(home + slope * x)))
        w = p * (1 - p)
        g = np.array([(y - p).sum(), ((y - p) * x).sum()])
        h = np.array([[w.sum(), (w * x).sum()], [(w * x).sum(), (w * x * x).sum()]])
        home, slope = np.array([home, slope]) + np.linalg.solve(h, g)
    return float(home), float(slope)


def net_rating_probabilities(games: pd.DataFrame, nets: NetRatings) -> pd.Series:
    """Each game's P(home wins), with the model fitted only on seasons that had already finished."""
    gaps = {}
    for r in games.itertuples():
        n = nets.before(r.season, r.date)
        gaps[(r.season, r.gamecode)] = n.get(r.home, 0.0) - n.get(r.away, 0.0)
    gap = pd.Series(gaps)
    out = {}
    seasons = sorted(games.season.unique())
    won = pd.Series({(r.season, r.gamecode): float(r.home_score > r.away_score) for r in games.itertuples()})
    for season in seasons:
        past = [s for s in seasons if s < season]
        if not past:
            continue
        mask = gap.index.get_level_values(0).isin(past)
        home, slope = fit_logistic(gap[mask].to_numpy(), won[mask].to_numpy())
        part = gap[gap.index.get_level_values(0) == season]
        for key, x in part.items():
            out[key] = float(1 / (1 + np.exp(-(home + slope * x))))
    return pd.Series(out)


def player_averages(pg: pd.DataFrame, stats: dict[str, str]) -> pd.DataFrame:
    """For each player-game: his season average and his last five games so far, from games he played.

    Before his first game of a season, last season's average stands in for both.
    """
    d = pg.sort_values(["player_id", "season", "date"])
    rows = []
    for pid, g in d.groupby("player_id", sort=False):
        last_season: dict[str, float] = {}
        for season, part in g.groupby("season", sort=True):
            history: list[dict] = []
            for r in part.itertuples():
                row = {"season": season, "gamecode": r.gamecode, "player_id": pid}
                if history:
                    recent = history[-5:]
                    for name in stats:
                        row[f"{name}_avg"] = float(np.mean([h[name] for h in history]))
                        row[f"{name}_last5"] = float(np.mean([h[name] for h in recent]))
                elif last_season:
                    for name in stats:
                        row[f"{name}_avg"] = last_season[name]
                        row[f"{name}_last5"] = last_season[name]
                rows.append(row)
                if r.minutes > 0:
                    history.append({name: float(getattr(r, col)) for name, col in stats.items()})
            if history:
                last_season = {name: float(np.mean([h[name] for h in history])) for name in stats}
    return pd.DataFrame(rows)
