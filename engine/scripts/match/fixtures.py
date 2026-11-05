"""The games to come: simulate them before they are played, and keep what was said.

    uv run python -m bk.ingest E2026 && uv run python -m bk.model.build && uv run python -m bk.ratings.build
    uv run python scripts/match/fixtures.py [--rounds 2] [--sims 2000]

A prediction is locked once written: a later run never rewrites a game that already has a report, so the
record stays honest. When a game has been played, its real result is added beside the prediction, big misses
included. Every prediction also goes into data/audit/match_predictions.csv, which is only ever added to.

Writes data/tables/match_fixtures/<id>.json and data/tables/match_fixtures.json.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import warnings
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from types import SimpleNamespace

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from bk.config import AUDIT_DIR, RAW_DIR, TABLES_DIR  # noqa: E402
from bk.match.model import build_team, likely_roster, snapshot  # noqa: E402
from bk.match.report import build_report, compare_saved, real_block, real_events  # noqa: E402
from bk.match.runner import actual_game  # noqa: E402
from bk.match.sim import Tuning  # noqa: E402
from bk.ratings.metrics_v2 import load_tables  # noqa: E402
from bk.team.standings import regulation_scores, standings  # noqa: E402

SEASON = "E2026"
DIR = TABLES_DIR / "match_fixtures"
OVERVIEW = TABLES_DIR / "match_fixtures.json"
LEDGER = AUDIT_DIR / "match_predictions.csv"
LEDGER_COLUMNS = ["id", "written_at", "tip_off", "round", "home", "away", "home_win", "home_mean", "away_mean", "margin_lo", "margin_hi", "total_mean", "model"]
SHOW_PLAYED_ROUNDS = 2


def schedule() -> list[dict]:
    rows = json.loads((RAW_DIR / SEASON / "games.json").read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows.get("data", [])
    out = []
    for r in rows:
        out.append({"id": f"{SEASON}-{r['gameCode']}", "gamecode": int(r["gameCode"]), "round": int(r["round"]) if not isinstance(r["round"], dict) else int(r["round"]["round"]),
                    "tip_off": r.get("utcDate"), "home": r["local"]["club"]["code"], "away": r["road"]["club"]["code"],
                    "home_name": r["local"]["club"].get("name"), "away_name": r["road"]["club"].get("name"), "played": bool(r.get("played"))})
    return sorted(out, key=lambda g: (g["tip_off"] or "", g["gamecode"]))


def model_mark() -> str:
    """Which settings wrote a prediction."""
    return hashlib.sha256(json.dumps(asdict(Tuning()), sort_keys=True).encode()).hexdigest()[:10]


def _write_one(args) -> dict:
    game, home, away, league, sims, ranks = args
    rep = build_report(SimpleNamespace(league=league), home, away, sims=sims, seed=game["gamecode"] * 10_000)
    rep |= {"id": game["id"], "season": SEASON, "gamecode": game["gamecode"], "round": game["round"], "tip_off": game["tip_off"], "written_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "model": model_mark(), "ranks": {home.code: ranks.get(home.code), away.code: ranks.get(away.code)}, "squad": "likely"}
    (DIR / f"{game['id']}.json").write_text(json.dumps(rep, ensure_ascii=False, default=float), encoding="utf-8")
    return {"id": game["id"], "written_at": rep["written_at"], "tip_off": game["tip_off"], "round": game["round"], "home": home.code, "away": away.code, "home_win": rep["home_win"],
            "home_mean": rep["score"]["home"]["mean"], "away_mean": rep["score"]["away"]["mean"], "margin_lo": rep["score"]["margin"]["lo"], "margin_hi": rep["score"]["margin"]["hi"],
            "total_mean": rep["score"]["total"]["mean"], "model": rep["model"]}


def add_results(t) -> int:
    """Put the real game beside any locked prediction whose game has been played."""
    played = pd.read_parquet(TABLES_DIR / "games.parquet")
    done = 0
    for path in sorted(DIR.glob("*.json")):
        rep = json.loads(path.read_text(encoding="utf-8"))
        if "comparison" in rep:
            continue
        row = played[(played.season == SEASON) & (played.gamecode == rep["gamecode"])]
        if row.empty:
            continue
        home, away = rep["home"]["code"], rep["away"]["code"]
        actual = actual_game(t, SEASON, rep["gamecode"], home, away)
        rep["comparison"] = compare_saved(rep, actual)
        ratings = {p["player_id"]: {"values": p["ratings"], "labels": p["labels"], "low_data": p["low_data"]} for code in (home, away) for p in rep["players"][code]}
        rep["real"] = real_block(real_events(t, SEASON, rep["gamecode"], home, away), home, away, ratings)
        path.write_text(json.dumps(rep, ensure_ascii=False, default=float), encoding="utf-8")
        done += 1
    return done


def record(reports: list[dict]) -> dict:
    """How the locked predictions have done so far. These are the blind ones."""
    finished = [r for r in reports if "comparison" in r]
    if not finished:
        return {"games": 0}
    c = [r["comparison"] for r in finished]
    margin_error = [abs((x["home"] - x["away"]) - r["score"]["margin"]["mean"]) for x, r in zip(c, finished)]
    p = np.clip([r["home_win"] for r in finished], 0.01, 0.99)
    y = np.array([x["home"] > x["away"] for x in c], dtype=float)
    return {"games": len(finished), "winner": float(np.mean([x["favored_won"] for x in c])), "margin_error": float(np.mean(margin_error)), "margin_in_range": float(np.mean([x["margin_in_range"] for x in c])),
            "total_in_range": float(np.mean([x["total_in_range"] for x in c])), "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))}


def history() -> dict:
    """The look back over all played games, with the settings tuned on them, so not a blind test."""
    out = {}
    for tag, name in (("", "known"), ("_likely", "likely")):
        path = AUDIT_DIR / f"match_scorecard{tag}_enriched.parquet"
        if not path.exists():
            continue
        g = pd.read_parquet(path)
        y = (g.h_pts_real > g.a_pts_real).astype(float)
        p = g.p_home.clip(0.01, 0.99)
        q = g.p_net.clip(0.01, 0.99)
        ok = q.notna()
        loss = lambda v, m: float(-(y[m] * np.log(v[m]) + (1 - y[m]) * np.log(1 - v[m])).mean())  # noqa: E731
        err = (g.h_pts_real - g.a_pts_real) - (g.h_pts_sim - g.a_pts_sim)
        out[name] = {"games": int(len(g)), "winner": float(((p > 0.5) == (y == 1)).mean()), "margin_error": float(err.abs().mean()), "margin_in_range": float(g.margin_in_80.mean()),
                     "total_in_range": float(g.total_in_80.mean()), "log_loss": loss(p, ok), "net_rating_loss": loss(q, ok)}
    return out


def write_overview(games: list[dict], t) -> None:
    reports = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in DIR.glob("*.json")}
    played_rounds = sorted({r["round"] for r in reports.values() if "comparison" in r})[-SHOW_PLAYED_ROUNDS:]
    rows = []
    for g in games:
        rep = reports.get(g["id"])
        if rep is None:
            continue
        if "comparison" in rep and rep["round"] not in played_rounds:
            continue
        row = {"id": g["id"], "round": g["round"], "tip_off": g["tip_off"], "home": rep["home"], "away": rep["away"], "ranks": rep.get("ranks", {}), "written_at": rep["written_at"],
               "expected": {"home": rep["score"]["home"]["mean"], "away": rep["score"]["away"]["mean"], "margin_lo": rep["score"]["margin"]["lo"], "margin_hi": rep["score"]["margin"]["hi"]},
               "typical": [rep["typical"]["home"], rep["typical"]["away"]], "tempo": rep["tempo"], "headline": rep["preview"][0]["text"] if rep["preview"] else "", "status": "played" if "comparison" in rep else "upcoming"}
        if "comparison" in rep:
            row["real"] = [rep["comparison"]["home"], rep["comparison"]["away"]]
            row["margin_in_range"] = rep["comparison"]["margin_in_range"]
            row["favored_won"] = rep["comparison"]["favored_won"]
        rows.append(row)
    out = {"season": SEASON, "games": rows, "record": record(list(reports.values())), "history": history(), "updated_at": datetime.now(UTC).isoformat(timespec="seconds")}
    OVERVIEW.write_text(json.dumps(out, ensure_ascii=False, default=float), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=2, help="how many unplayed rounds to write")
    ap.add_argument("--sims", type=int, default=2000)
    a = ap.parse_args()
    DIR.mkdir(parents=True, exist_ok=True)
    t = load_tables()
    games = schedule()
    print("results added:", add_results(t), flush=True)
    upcoming = [g for g in games if not g["played"]]
    next_rounds = sorted({g["round"] for g in upcoming})[:a.rounds]
    # a game whose tip-off has passed gets no new prediction, whatever the feed says about it
    now = datetime.now(UTC).isoformat()
    targets = [g for g in upcoming if g["round"] in next_rounds and not (DIR / f"{g['id']}.json").exists() and (g["tip_off"] or "") > now[:19]]
    print("to write:", [g["id"] for g in targets], flush=True)
    if targets:
        snap = snapshot(t, SEASON)
        table = standings(pd.read_parquet(TABLES_DIR / "games.parquet"), SEASON, regulation_scores(t.events, pd.read_parquet(TABLES_DIR / "games.parquet")))
        ranks = {r["code"]: {"rank": r["rank"], "wins": r["wins"], "losses": r["losses"]} for r in table}
        jobs = [(g, build_team(snap, g["home"], likely_roster(snap, g["home"])), build_team(snap, g["away"], likely_roster(snap, g["away"])), snap.league, a.sims, ranks) for g in targets]
        with ProcessPoolExecutor(8) as pool:
            written = list(pool.map(_write_one, jobs))
        new_file = not LEDGER.exists()
        with LEDGER.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS)
            if new_file:
                writer.writeheader()
            writer.writerows(written)
    write_overview(games, t)
    print("overview written", flush=True)


if __name__ == "__main__":
    main()
