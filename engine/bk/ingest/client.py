"""Cached, rate-limited client for the public EuroLeague endpoints.

Raw responses are stored verbatim under data/raw/{season}/... so every later
stage can be rebuilt offline. A file that already exists is never re-fetched,
which makes ingest idempotent and polite to the source.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from bk.config import COMPETITION, RAW_DIR

LIVE_BASE = "https://live.euroleague.net/api"
V2_BASE = "https://api-live.euroleague.net/v2"
USER_AGENT = "ball-knowledge/0.1 (non-commercial research prototype)"

GAME_KINDS = ("PlaybyPlay", "Points", "Boxscore")


class EuroleagueClient:
    # live.euroleague.net starts answering 429 after ~60 quick requests, so stay well below that
    def __init__(self, raw_dir: Path = RAW_DIR, min_interval: float = 1.2, timeout: float = 30.0):
        self.raw_dir = raw_dir
        self.min_interval = min_interval
        self._last = 0.0
        self._http = httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT})

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "EuroleagueClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- low level -----------------------------------------------------------
    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any | None:
        """GET with rate limit and retries. Returns None for empty bodies."""
        for attempt in range(6):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self._http.get(url, params=params)
            except httpx.TransportError:
                time.sleep(2**attempt)
                continue
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After", "")
                time.sleep(int(retry_after) if retry_after.isdigit() else 60 * (attempt + 1))
                continue
            if r.status_code in (500, 502, 503, 504):
                time.sleep(2**attempt)
                continue
            r.raise_for_status()
            text = r.text.strip()
            return json.loads(text) if text else None
        raise RuntimeError(f"giving up on {url} {params}")

    @staticmethod
    def _write(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    # -- public --------------------------------------------------------------
    def games(self, season: str, refresh: bool = True) -> list[dict]:
        """Season schedule. Refreshed by default because results change during a season."""
        path = self.raw_dir / season / "games.json"
        if refresh or not path.exists():
            data = self._get_json(f"{V2_BASE}/competitions/{COMPETITION}/seasons/{season}/games")
            self._write(path, data)
        return json.loads(path.read_text(encoding="utf-8"))["data"]

    def game_path(self, season: str, gamecode: int, kind: str) -> Path:
        return self.raw_dir / season / f"{gamecode:03d}" / f"{kind}.json"

    def game_file(self, season: str, gamecode: int, kind: str) -> tuple[Any | None, bool]:
        """Return (data, fetched_now). Cached files are returned without a request."""
        path = self.game_path(season, gamecode, kind)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), False
        data = self._get_json(f"{LIVE_BASE}/{kind}", {"gamecode": gamecode, "seasoncode": season})
        if data:  # never cache an empty body (game not played / feed not ready)
            self._write(path, data)
        return data, True
