"""Do simulated players look like their ratings? Checked on the E2025 development games.

    uv run python scripts/match/rating_overlap.py [--sims 60]

Adds up each player's simulated games over the season sample, then compares with the 1-20 number he
carried into those games, and with what he really did in the same games as a yardstick. A simulator
that follows the ratings should rank players at least as the ratings do.

Writes data/audit/match_rating_overlap.md.
"""

from __future__ import annotations

import argparse
import pickle
import warnings
from concurrent.futures import ProcessPoolExecutor

warnings.filterwarnings("ignore")

import pandas as pd  # noqa: E402

from bk.config import AUDIT_DIR, DATA_DIR  # noqa: E402
from bk.match.model import load_league  # noqa: E402
from bk.match.runner import run_many  # noqa: E402
from bk.ratings.metrics_v2 import THREE_BASE_PCT  # noqa: E402

CACHE = DATA_DIR / "match_cache" / "scorecard_games.pkl"
MIN_MINUTES = 200.0
GATE_RHO = 0.75
COLUMNS = ["sec", "pts", "f2m", "f2a", "f3m", "f3a", "ftm", "fta", "orb", "drb", "ast", "stl", "blk", "tov", "pf", "self"]


def z(x: pd.Series) -> pd.Series:
    return (x - x.mean()) / (x.std() or 1.0)


def per36(b: pd.DataFrame, column: str) -> pd.Series:
    return 36 * 60 * b[column] / b.sec


def touches(b: pd.DataFrame) -> pd.Series:
    return b.f2a + b.f3a + 0.44 * b.fta + b.ast + b.tov


def three_point(b: pd.DataFrame) -> pd.Series:
    """The rating is points above a base shooter per game: attempts times accuracy above the base."""
    return per36(b, "f3a") * (b.f3m / b.f3a.clip(lower=1) - THREE_BASE_PCT)


# Each reading matches how the rating is defined, or the comparison would test the wrong thing.
# rating -> (label, how to read the same thing from a box line, who is rated at all)
CHECKS = {
    "three_point": ("Üçlük (deneme x isabet üstü)", three_point, lambda b: b.f3a >= 25),
    "free_throw": ("Serbest Atış", lambda b: b.ftm / b.fta.clip(lower=1), lambda b: b.fta >= 20),
    "passing": ("Pas", lambda b: per36(b, "ast"), None),
    "off_rebounding": ("Hücum Ribaundu", lambda b: per36(b, "orb"), None),
    "def_rebounding": ("Savunma Ribaundu", lambda b: per36(b, "drb"), None),
    "steals": ("Top Çalma", lambda b: per36(b, "stl"), None),
    "shot_blocking": ("Blok", lambda b: per36(b, "blk"), None),
    "drawing_fouls": ("Faul Alma", lambda b: per36(b, "fta"), None),
    "discipline": ("Faul Disiplini", lambda b: -per36(b, "pf"), None),
    "shot_creation": ("Şut Yaratma (asistsiz sayı)", lambda b: per36(b, "self"), None),
    "finishing": ("Bitiricilik", lambda b: per36(b, "f2m"), None),
    "ball_care": ("Top Koruma (simülatörün okuduğu gizli puan)", lambda b: -b.tov / touches(b).clip(lower=1), None),
}


def spearman(a: pd.Series, b: pd.Series) -> float:
    return float(a.rank().corr(b.rank()))


def _one(args):
    game, league, sims = args
    m = run_many(game["home"], game["away"], league, None, sims, seed=game["gamecode"] * 1000)
    rows = []
    for side, team in ((0, m.home), (1, m.away)):
        means = m.players[side].mean(axis=0)
        for j, p in enumerate(team.players):
            row = {"player_id": p.player_id, "player": p.name, **{c: float(v) for c, v in zip(m.box_columns, means[j])}}
            real = game["actual"]["players"].get(p.player_id, {})
            row.update({f"real_{c}": float(real.get(c, 0.0)) for c in COLUMNS})
            row.update({f"r_{k}": v for k, v in p.ratings.items()})
            rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=60)
    a = ap.parse_args()
    games = [g for g in pickle.loads(CACHE.read_bytes()) if g["season"] == "E2025"]
    league = load_league()
    with ProcessPoolExecutor(8) as pool:
        rows = [r for part in pool.map(_one, [(g, league, a.sims) for g in games], chunksize=4) for r in part]
    d = pd.DataFrame(rows)
    sim = d.groupby("player_id")[COLUMNS].sum()
    real = d.groupby("player_id")[[f"real_{c}" for c in COLUMNS]].sum()
    real.columns = COLUMNS
    # the rating a player carried in, averaged over the games, since it moves through the season
    ratings = d.groupby("player_id")[[c for c in d.columns if c.startswith("r_")]].mean()
    keep = sim.sec >= MIN_MINUTES * 60
    lines = ["# Simülasyon ve oyuncu puanları", "", f"{len(games)} E2025 maçı, {int(keep.sum())} oyuncu (en az {MIN_MINUTES:.0f} dakika).",
             "Spearman sıra korelasyonu. Sağdaki sütun, aynı oyuncuların gerçek maçlardaki rakamlarıyla puan arasındaki ilişkidir.", "",
             "| Puan | Simülasyon ↔ puan | Gerçek ↔ puan | Eşik |", "|---|---:|---:|---:|"]
    failed = []
    for key, (label, read, usable) in CHECKS.items():
        col = f"r_{key}"
        if col not in ratings:
            continue
        mask = keep if usable is None else keep & usable(sim)
        rho_sim = spearman(read(sim[mask]), ratings.loc[mask, col])
        mask_real = keep if usable is None else keep & usable(real)
        rho_real = spearman(read(real[mask_real]), ratings.loc[mask_real, col])
        ok = rho_sim >= GATE_RHO
        if not ok:
            failed.append(label)
        lines.append(f"| {label} | {rho_sim:.2f} | {rho_real:.2f} | {'geçti' if ok else 'KALDI'} |")
    lines += ["", "Geçemeyenler: " + (", ".join(failed) if failed else "yok")]
    out = "\n".join(lines) + "\n"
    (AUDIT_DIR / "match_rating_overlap.md").write_text(out, encoding="utf-8")
    print(out.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
