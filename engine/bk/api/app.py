"""HTTP API for the web app.

    uv run uvicorn bk.api.app:app --reload --port 8000
"""

from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from bk.config import TABLES_DIR
from bk.ratings.catalog import ATTR_BY_KEY, HINTS, RATING_ATTRIBUTES, display_kind
from bk.ratings.metrics_v2 import display_value
from bk.sim import profiles
from bk.sim.engine import Context, SetSimulator
from bk.sim.library import LIBRARY
from bk.sim.params import SimParams

app = FastAPI(title="Ball Knowledge API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ATTR_KEYS = [a.key for a in RATING_ATTRIBUTES]
LEADER_MIN_MPG = 10  # a good rate in a very small role does not make a league leader


@lru_cache(maxsize=1)
def T() -> dict[str, pd.DataFrame]:
    names = ["ratings_season", "ratings_month", "game_ratings", "shots", "games", "player_metrics"]
    return {n: pd.read_parquet(TABLES_DIR / f"{n}.parquet") for n in names}


def records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def latest_season() -> str:
    return str(T()["ratings_season"].season.max())


def _round(value, digits: int) -> float | None:
    return None if pd.isna(value) else round(float(value), digits)


def team_names(season: str) -> dict[str, str]:
    g = T()["games"]
    g = g[g.season == season]
    names = dict(zip(g.home, g.home_name))
    names.update(dict(zip(g.away, g.away_name)))
    return names


def _display(row, key: str) -> str:
    return display_value(key, int(row[key]), bool(row.get("three_non_shooter", False)), int(row["games"]),
                         bool(row.get("mid_non_shooter", False)))


def _ratings(row: pd.Series) -> list[dict]:
    return [{"key": k, "value": int(row[k]), "lo": int(row[f"{k}_lo"]), "hi": int(row[f"{k}_hi"]),
             "low_data": bool(row[f"{k}_low_data"]), "conf": float(row[f"{k}_conf"]), "display": _display(row, k)} for k in ATTR_KEYS]


def _labels(row) -> dict[str, str]:
    """Attributes that show something other than their number."""
    return {k: _display(row, k) for k in ATTR_KEYS if _display(row, k) != str(int(row[k]))}


# ---- meta -------------------------------------------------------------------------
@lru_cache(maxsize=1)
def league_ppp() -> dict[str, float]:
    po = pd.read_parquet(TABLES_DIR / "possessions.parquet", columns=["season", "points"])
    return po.groupby("season").points.mean().round(3).to_dict()


@app.get("/api/meta")
def meta():
    seasons = sorted(T()["ratings_season"].season.unique().tolist(), reverse=True)
    return {
        "seasons": seasons, "latest": seasons[0], "league_ppp": league_ppp(),
        "attributes": [{"key": a.key, "label": a.label, "group": a.group, "source": a.source,
                        "description": a.description, "display": display_kind(a.key), "hint": HINTS[a.key]} for a in RATING_ATTRIBUTES],
        "sim_params": SimParams.load().to_dict(),
    }


# ---- players ----------------------------------------------------------------------
@app.get("/api/players")
def players(season: str | None = None, team: str | None = None, q: str | None = None,
            sort: str = "minutes", qualified_only: bool = True, rated_only: bool = False,
            limit: int = Query(400, le=1000)):
    """rated_only is for leader lists: enough data on the sort attribute and a real role in the team."""
    season = season or latest_season()
    r = T()["ratings_season"]
    r = r[r.season == season]
    if qualified_only:
        r = r[r.qualified]
    if team:
        r = r[r.team == team]
    if q:
        r = r[r.player.str.contains(q, case=False, na=False)]
    if sort not in r.columns:
        raise HTTPException(400, f"unknown sort {sort}")
    if rated_only and sort in ATTR_KEYS:
        r = r[~r[f"{sort}_low_data"] & (r.mpg >= LEADER_MIN_MPG)]
        if sort == "three_point":
            r = r[~r.three_non_shooter]
        if sort == "mid_range":
            r = r[~r.mid_non_shooter]
    r = r.sort_values(sort, ascending=False).head(limit)
    names = team_names(season)
    cols = ["player_id", "player", "team", "games", "minutes", "mpg"] + ATTR_KEYS
    out = records(r[cols].round({"minutes": 0, "mpg": 1}))
    for o, (_, row) in zip(out, r.iterrows()):
        o["team_name"] = names.get(o["team"], o["team"])
        o["labels"] = _labels(row)
    return {"season": season, "players": out}


@app.get("/api/players/{player_id}")
def player(player_id: str, season: str | None = None):
    t = T()
    season = season or latest_season()
    rs = t["ratings_season"]
    row = rs[(rs.season == season) & (rs.player_id == player_id)]
    if row.empty:
        raise HTTPException(404, "player not found for season")
    row = row.iloc[0]
    rm = t["ratings_month"]
    months = rm[(rm.season == season) & (rm.player_id == player_id)].sort_values("month")
    gr = t["game_ratings"]
    games = gr[(gr.season == season) & (gr.player_id == player_id)].sort_values("date")
    g = t["games"]
    g = g[g.season == season][["gamecode", "round", "home", "away", "home_score", "away_score"]]
    games = games.merge(g, on="gamecode", how="left")
    sh = t["shots"]
    sh = sh[(sh.season == season) & (sh.player_id == player_id) & sh.x.notna()]
    met = t["player_metrics"]
    met = met[(met.season == season) & (met.player_id == player_id)].iloc[0]
    other_seasons = sorted(rs[rs.player_id == player_id].season.unique().tolist(), reverse=True)
    n_games = max(int(row["games"]), 1)
    totals = games[["pts", "orb", "drb", "ast", "stl", "blk", "tov", "pir", "fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta"]].sum()
    clutch_plays = float(met["clutch_use"])
    return {
        "season": season, "seasons": other_seasons,
        "player": {"player_id": player_id, "name": row["player"], "team": row["team"],
                   "team_name": team_names(season).get(row["team"], row["team"]),
                   "games": int(row["games"]), "minutes": round(float(row["minutes"]), 1),
                   "mpg": round(float(row["mpg"]), 1), "qualified": bool(row["qualified"])},
        "ratings": _ratings(row),
        "per_game": {k: round(float(totals[k]) / n_games, 1) for k in ["pts", "ast", "stl", "blk", "tov", "pir"]}
                    | {"reb": round(float(totals.orb + totals.drb) / n_games, 1),
                       "fg2_pct": round(float(totals.fg2m) / max(float(totals.fg2a), 1), 3),
                       "fg3_pct": round(float(totals.fg3m) / max(float(totals.fg3a), 1), 3),
                       "ft_pct": round(float(totals.ftm) / max(float(totals.fta), 1), 3),
                       "fg3m": round(float(totals.fg3m) / n_games, 1), "fg3a": round(float(totals.fg3a) / n_games, 1)},
        "shooting": {z: round(float(met[c]), 3) for z, c in
                     [("inside", "inside_adj"), ("mid", "mid_pct"), ("corner3", "corner3_pct"), ("three", "three_pct"),
                      ("ft", "ft_pct")]},
        "info": {
            "clutch": {"points": int(met["clutch_points"]), "plays": round(clutch_plays, 1),
                       "per_play": round(float(met["clutch_points"]) / clutch_plays, 2) if clutch_plays > 0 else None},
            "corner3_attempts": int(float(met["n_corner3_pct"])),
            "inside_on_off": {"fga_on": _round(met["opp_inside_fga_on"], 1), "fga_off": _round(met["opp_inside_fga_off"], 1),
                              "pct_on": _round(met["opp_inside_pct_on"], 3), "pct_off": _round(met["opp_inside_pct_off"], 3)},
        },
        "months": [{"month": m["month"], "games": int(m["games"]), "ratings": _ratings(m)} for _, m in months.iterrows()],
        "games": records(games[["gamecode", "date", "round", "team", "opponent", "is_home", "minutes", "pts",
                                "orb", "drb", "ast", "stl", "blk", "tov", "pir", "plus_minus", "gmsc",
                                "game_rating", "short_game", "home_score", "away_score"]].round({"minutes": 1, "gmsc": 1})),
        "shots": records(sh[["x", "y", "made", "zone", "value", "assisted"]]),
    }


# ---- teams ------------------------------------------------------------------------
@app.get("/api/teams")
def teams(season: str | None = None):
    season = season or latest_season()
    r = T()["ratings_season"]
    r = r[(r.season == season)]
    names = team_names(season)
    agg = r[r.qualified].groupby("team")[ATTR_KEYS].mean().round(1)
    return {"season": season, "teams": [{"code": c, "name": names.get(c, c), "avg": records(agg.loc[[c]])[0]}
                                        for c in sorted(agg.index)]}


@app.get("/api/teams/{code}")
def team(code: str, season: str | None = None):
    season = season or latest_season()
    r = T()["ratings_season"]
    r = r[(r.season == season) & (r.team == code)].sort_values("minutes", ascending=False)
    if r.empty:
        raise HTTPException(404, "team not found")
    cols = ["player_id", "player", "games", "minutes", "mpg", "qualified"] + ATTR_KEYS
    roster = records(r[cols].round({"minutes": 0, "mpg": 1}))
    for o, (_, row) in zip(roster, r.iterrows()):
        o["labels"] = _labels(row)
    return {"season": season, "code": code, "name": team_names(season).get(code, code), "roster": roster}


# ---- coach: sets & simulation -------------------------------------------------------
@app.get("/api/sets")
def sets():
    return {"sets": list(LIBRARY.values())}


class SimContext(BaseModel):
    stint_minutes: float = Field(4.0, ge=0, le=40)
    clutch: bool = False


class SimRequest(BaseModel):
    set: dict
    season: str | None = None
    offense: dict[str, str]  # slot -> player_id
    defense: dict[str, str]  # slot guarded -> player_id
    context: SimContext = SimContext()
    iterations: int = Field(10_000, ge=500, le=50_000)
    sensitivity: bool = True


@app.post("/api/simulate")
def simulate(req: SimRequest):
    season = req.season or latest_season()
    slots = {"1", "2", "3", "4", "5"}
    if set(req.offense) != slots or set(req.defense) != slots:
        raise HTTPException(400, "offense and defense must assign slots 1-5")
    try:
        off = {s: profiles.load_player(season, pid) for s, pid in req.offense.items()}
        dfn = {s: profiles.load_player(season, pid) for s, pid in req.defense.items()}
        sim = SetSimulator(req.set, off, dfn, ctx=Context(**req.context.model_dump()),
                           baseline=profiles.league_average(season))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    result = sim.simulate(req.iterations)
    if req.sensitivity:
        result["sensitivity"] = sim.sensitivity(max(2000, req.iterations // 3))
    result["params"] = {"calibrated": list(sim.p.calibrated_keys)}
    return result


@app.post("/api/reload")
def reload_tables():
    T.cache_clear()
    league_ppp.cache_clear()
    profiles.clear_cache()
    return {"ok": True}


@app.get("/api/attributes/{key}/leaders")
def leaders(key: str, season: str | None = None, limit: int = 10):
    if key not in ATTR_BY_KEY:
        raise HTTPException(404, "unknown attribute")
    return players(season=season, sort=key, rated_only=True, limit=limit)
