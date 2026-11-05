"""Compare our table with the official one, round by round.

    uv run python scripts/audit/standings_check.py [--step 3]

Calls the public standings feed once per round checked, with a pause between calls.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
import warnings

warnings.filterwarnings("ignore")

import pandas as pd  # noqa: E402

from bk.config import TABLES_DIR  # noqa: E402
from bk.team.standings import regulation_scores, standings  # noqa: E402

URL = "https://api-live.euroleague.net/v3/competitions/E/seasons/{season}/rounds/{round}/basicstandings"


def official(season: str, rnd: int) -> list[dict]:
    req = urllib.request.Request(URL.format(season=season, round=rnd), headers={"User-Agent": "ball-knowledge-check"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return data.get("teams") or data.get("data") or []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=3)
    a = ap.parse_args()
    games = pd.read_parquet(TABLES_DIR / "games.parquet")
    events = pd.read_parquet(TABLES_DIR / "events.parquet", columns=["season", "gamecode", "type", "team", "period"])
    regulation = regulation_scores(events, games)
    checked = wrong_places = wrong_numbers = 0
    for season in sorted(games.season.unique()):
        last = int(games[(games.season == season) & (games.phase == "RS")]["round"].max())
        rounds = sorted({*range(a.step, last, a.step), last})
        for rnd in rounds:
            part = games[(games.season == season) & ((games.phase != "RS") | (games["round"] <= rnd))]
            mine = standings(part, season, regulation)
            theirs = official(season, rnd)
            places = [(i + 1, t["club"]["code"], m["code"]) for i, (t, m) in enumerate(zip(theirs, mine)) if t["club"]["code"] != m["code"]]
            by_code = {m["code"]: m for m in mine}
            numbers = [t["club"]["code"] for t in theirs if (t["gamesWon"], t["gamesLost"], int(str(t["pointsDifference"]).replace("+", ""))) !=
                       (by_code[t["club"]["code"]]["wins"], by_code[t["club"]["code"]]["losses"], by_code[t["club"]["code"]]["diff"])]
            checked += 1
            wrong_places += len(places)
            wrong_numbers += len(numbers)
            if places or numbers:
                print(season, rnd, "places", places[:4], "numbers", numbers[:6])
            time.sleep(1.3)
    print(f"{checked} rounds checked: {wrong_places} places and {wrong_numbers} team lines differ")


if __name__ == "__main__":
    main()
