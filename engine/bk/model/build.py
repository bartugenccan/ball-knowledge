"""Build analysis tables (Parquet) from the raw JSON cache.

    uv run python -m bk.model.build
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from bk.config import RAW_DIR, TABLES_DIR
from bk.model.clean import (flag_possessions, flag_rebounds, flag_shots, fouls_table, ft_trips, link_blocks,
                            parse_official, parse_people)
from bk.model.parse import GameTables, parse_game

TABLES = ("events", "shots", "possessions", "player_games", "stints", "rebound_chances")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def iter_games(raw_dir: Path = RAW_DIR):
    for season_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        season = season_dir.name
        meta = {g["gameCode"]: g for g in (_load(season_dir / "games.json") or {}).get("data", [])}
        for game_dir in sorted(p for p in season_dir.iterdir() if p.is_dir()):
            code = int(game_dir.name)
            pbp, pts, box = (_load(game_dir / f"{k}.json") for k in ("PlaybyPlay", "Points", "Boxscore"))
            if pbp and box:
                yield season, code, pbp, pts, box, meta.get(code, {})


def reference_tables(raw_dir: Path = RAW_DIR) -> dict[str, pd.DataFrame]:
    """Per-season roster data and official totals, when they have been ingested."""
    people: list[dict] = []
    official: list[dict] = []
    for season_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        people += parse_people(_load(season_dir / "people.json"), season_dir.name)
        official += parse_official(_load(season_dir / "official_players.json"), season_dir.name)
    return {"people": pd.DataFrame(people), "official_totals": pd.DataFrame(official)}


def build(raw_dir: Path = RAW_DIR, out_dir: Path = TABLES_DIR) -> dict[str, pd.DataFrame]:
    acc = GameTables()
    games = []
    for season, code, pbp, pts, box, meta in iter_games(raw_dir):
        t = parse_game(season, code, pbp, pts, box, meta)
        for name in TABLES:
            getattr(acc, name).extend(getattr(t, name))
        games.append({
            "season": season, "gamecode": code, "date": meta.get("utcDate") or meta.get("date"),
            "phase": (meta.get("phaseType") or {}).get("code"),
            "round": (meta.get("round") if isinstance(meta.get("round"), int) else None),
            "home": (pbp.get("CodeTeamA") or "").strip(), "away": (pbp.get("CodeTeamB") or "").strip(),
            "home_name": pbp.get("TeamA"), "away_name": pbp.get("TeamB"),
            "home_score": (meta.get("local") or {}).get("score"),
            "away_score": (meta.get("road") or {}).get("score"),
        })
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = {name: pd.DataFrame(getattr(acc, name)) for name in TABLES}
    frames["games"] = pd.DataFrame(games)

    events = frames["events"]
    frames["fouls"] = fouls_table(events)
    frames["ft_trips"] = ft_trips(events, frames["fouls"])
    frames["shots"] = link_blocks(flag_shots(frames["shots"]), events)
    frames["possessions"] = flag_possessions(frames["possessions"])
    frames["rebound_chances"] = flag_rebounds(frames["rebound_chances"], events)
    frames.update(reference_tables(raw_dir))

    for name, df in frames.items():
        if "date" in df:
            df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
    return frames


if __name__ == "__main__":
    for name, df in build().items():
        print(f"{name:16s} {len(df):>8,} rows")
