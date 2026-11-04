"""Download all played games for the given seasons.

    uv run python -m bk.ingest E2024 E2025 E2026
"""

from __future__ import annotations

import sys

from bk.ingest.client import GAME_KINDS, EuroleagueClient


def main(seasons: list[str]) -> None:
    with EuroleagueClient() as client:
        for season in seasons:
            games = [g for g in client.games(season) if g.get("played")]
            for fetch in (client.people, client.official_player_totals):
                try:
                    fetch(season)
                except Exception as e:  # reference data must not block game ingest
                    print(f"{season}: {fetch.__name__} FAILED: {e}", flush=True)
            fetched = missing = 0
            failed: list[str] = []
            for i, g in enumerate(sorted(games, key=lambda g: g["gameCode"]), 1):
                for kind in GAME_KINDS:
                    try:
                        data, now = client.game_file(season, g["gameCode"], kind)
                    except Exception as e:  # keep going; a re-run fills the gaps
                        failed.append(f"{g['gameCode']}/{kind}: {e}")
                        continue
                    fetched += now
                    missing += data is None
                if i % 50 == 0:
                    print(f"{season}: {i}/{len(games)} games", flush=True)
            print(f"{season}: {len(games)} played games, {fetched} requests, {missing} empty, "
                  f"{len(failed)} failed", flush=True)
            for f in failed[:20]:
                print("  FAILED", f, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["E2025"])
