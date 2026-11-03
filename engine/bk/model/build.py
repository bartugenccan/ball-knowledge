"""Build analysis tables (Parquet) from the raw JSON cache.

    uv run python -m bk.model.build
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from bk.config import RAW_DIR, TABLES_DIR
from bk.model.parse import GameTables, parse_game

TABLES = ("events", "shots", "possessions", "player_games", "stints")


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
    for name, df in frames.items():
        if "date" in df:
            df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
    return frames


if __name__ == "__main__":
    for name, df in build().items():
        print(f"{name:13s} {len(df):>8,} rows")
