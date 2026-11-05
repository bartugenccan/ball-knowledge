"""The regular-season table, worked out from the played games.

Wins decide first. Teams level on wins are then separated by their games against each other, but only
once every tied pair has played both its games; until then, and after that, by points difference, then
points scored. Points difference leaves out overtime. These rules were read off the official tables:
scripts/audit/standings_check.py compares every round with them.
"""

from __future__ import annotations

import pandas as pd

PLAYOFF_PLACES = 6
PLAY_IN_PLACES = 10
POINTS = {"2FGM": 2, "3FGM": 3, "FTM": 1}


def regulation_scores(events: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Each game's score at the end of the fourth quarter, added up from the baskets."""
    e = events[events.type.isin(list(POINTS)) & (events.period <= 4)]
    e = e.assign(pts=e.type.map(POINTS)).merge(games[["season", "gamecode", "home"]], on=["season", "gamecode"])
    e["side"] = (e.team == e.home).map({True: "reg_home", False: "reg_away"})
    wide = e.pivot_table(index=["season", "gamecode"], columns="side", values="pts", aggfunc="sum", fill_value=0)
    return wide.reset_index()


def _prepare(games: pd.DataFrame, regulation: pd.DataFrame | None) -> pd.DataFrame:
    played = games[(games.phase == "RS") & games.home_score.notna() & games.away_score.notna()].sort_values("date")
    if regulation is not None:
        played = played.merge(regulation, on=["season", "gamecode"], how="left")
    else:
        played = played.assign(reg_home=played.home_score, reg_away=played.away_score)
    return played.assign(reg_home=played.reg_home.fillna(played.home_score), reg_away=played.reg_away.fillna(played.away_score))


def _row(code: str, name: str, part: pd.DataFrame) -> dict:
    wins = home_wins = home_games = away_wins = away_games = scored = allowed = counted_for = counted_against = 0
    results: list[bool] = []
    for g in part.itertuples():
        at_home = g.home == code
        own, other = (g.home_score, g.away_score) if at_home else (g.away_score, g.home_score)
        reg_own, reg_other = (g.reg_home, g.reg_away) if at_home else (g.reg_away, g.reg_home)
        won = own > other
        results.append(won)
        wins += won
        scored += own
        allowed += other
        counted_for += reg_own
        counted_against += reg_other
        if at_home:
            home_games += 1
            home_wins += won
        else:
            away_games += 1
            away_wins += won
    streak = 0
    for won in reversed(results):
        if won != results[-1]:
            break
        streak += 1
    return {"code": code, "name": name, "games": len(results), "wins": int(wins), "losses": len(results) - int(wins), "scored": int(scored), "allowed": int(allowed),
            "points_for": int(counted_for), "points_against": int(counted_against), "diff": int(counted_for - counted_against),
            "home": f"{home_wins}-{home_games - home_wins}", "away": f"{away_wins}-{away_games - away_wins}", "last5": [bool(x) for x in results[-5:]],
            "streak": ("G" if results and results[-1] else "M") + str(streak) if results else "-"}


def _order(group: list[dict], played: pd.DataFrame) -> list[dict]:
    if len(group) < 2:
        return group
    codes = {r["code"] for r in group}
    part = played[played.home.isin(codes) & played.away.isin(codes)]
    both_legs = len(part.groupby(["home", "away"]).size()) == len(codes) * (len(codes) - 1)
    if not both_legs:
        return sorted(group, key=lambda r: (-r["diff"], -r["points_for"], r["code"]))
    h2h = dict.fromkeys(codes, (0, 0))
    for g in part.itertuples():
        for code, own, other, reg_own, reg_other in ((g.home, g.home_score, g.away_score, g.reg_home, g.reg_away), (g.away, g.away_score, g.home_score, g.reg_away, g.reg_home)):
            w, d = h2h[code]
            h2h[code] = (w + int(own > other), d + int(reg_own - reg_other))
    return sorted(group, key=lambda r: (-h2h[r["code"]][0], -h2h[r["code"]][1], -r["diff"], -r["points_for"], r["code"]))


def standings(games: pd.DataFrame, season: str, regulation: pd.DataFrame | None = None) -> list[dict]:
    season_games = games[games.season == season]
    played = _prepare(season_games, regulation)
    names = dict(zip(season_games.home, season_games.home_name)) | dict(zip(season_games.away, season_games.away_name))
    rows = [_row(code, names.get(code, code), played[(played.home == code) | (played.away == code)]) for code in sorted(names)]
    table: list[dict] = []
    for wins in sorted({r["wins"] for r in rows}, reverse=True):
        table += _order([r for r in rows if r["wins"] == wins], played)
    for i, r in enumerate(table, 1):
        r["rank"] = i
        r["zone"] = "playoff" if i <= PLAYOFF_PLACES else "playin" if i <= PLAY_IN_PLACES else None
    return table
