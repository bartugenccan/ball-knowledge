"""Simulator results under the old and the new ratings, on the same matchups.

    uv run python scripts/audit/sim_compare.py [old_calibration.json]

Read-only: writes only under data/audit/. Old ratings come from the *_v1 tables. When an old
calibration file is given, the old run uses those parameters.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from foundation import table  # noqa: E402

from bk.config import AUDIT_DIR, TABLES_DIR  # noqa: E402
from bk.ratings.attributes import ATTRIBUTES as OLD_ATTRIBUTES  # noqa: E402
from bk.ratings.catalog import RATING_ATTRIBUTES  # noqa: E402
from bk.sim import profiles  # noqa: E402
from bk.sim.engine import Context, Player, SetSimulator  # noqa: E402
from bk.sim.library import LIBRARY  # noqa: E402
from bk.sim.params import SimParams  # noqa: E402

SEASON = "E2025"
ITERATIONS = 4000
MATCHUPS = 12
SEED = 7


def lineup(ratings: pd.DataFrame, team: str) -> list[str]:
    """The team's five biggest minute loads."""
    return ratings[ratings.team == team].sort_values("minutes", ascending=False).head(5).player_id.tolist()


def loader(ratings: pd.DataFrame, metrics: pd.DataFrame, attributes):
    r = ratings.set_index(["season", "player_id"])
    m = metrics.set_index(["season", "player_id"])

    def load(pid: str) -> Player:
        row, met = r.loc[(SEASON, pid)], m.loc[(SEASON, pid)]
        pct = {k: float(met[c]) if c in met else float(met[k]) for k, c in profiles.PCT_SOURCE.items()}
        return Player(player_id=pid, name=pid, ratings=profiles.sim_ratings(row, attributes), pct=pct)

    return load


def baseline(ratings: pd.DataFrame, metrics: pd.DataFrame) -> Player:
    ids = ratings[(ratings.season == SEASON) & ratings.qualified].player_id
    mean = metrics[(metrics.season == SEASON) & metrics.player_id.isin(ids)].mean(numeric_only=True)
    pct = {k: float(mean[c]) if c in mean else float(mean[k]) for k, c in profiles.PCT_SOURCE.items()}
    return Player.average(pct=pct)


def main() -> None:
    read = lambda n: pd.read_parquet(TABLES_DIR / f"{n}.parquet")  # noqa: E731
    new_r, new_m, old_r, old_m = read("ratings_season"), read("player_metrics"), read("ratings_season_v1"), read("player_metrics_v1")
    e = new_r[new_r.season == SEASON]
    rng = np.random.default_rng(SEED)
    teams = sorted(e.team.unique())
    pairs = [tuple(rng.choice(teams, 2, replace=False)) for _ in range(MATCHUPS)]
    new_params = SimParams.load()
    old_params = SimParams.load()
    if len(sys.argv) > 1:
        for k, v in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")).items():
            if hasattr(old_params, k):
                setattr(old_params, k, v)
    versions = {"eski": (loader(old_r, old_m, OLD_ATTRIBUTES), baseline(old_r, old_m), old_params),
                "yeni": (loader(new_r, new_m, RATING_ATTRIBUTES), baseline(new_r, new_m), new_params)}
    rows = []
    for set_id, set_def in LIBRARY.items():
        for off_team, def_team in pairs:
            off_ids, def_ids = lineup(e, off_team), lineup(e, def_team)
            if len(off_ids) < 5 or len(def_ids) < 5:
                continue
            row = {"set": set_id, "offense": off_team, "defense": def_team}
            for name, (load, base, params) in versions.items():
                off = {str(i + 1): load(p) for i, p in enumerate(off_ids)}
                dfn = {str(i + 1): load(p) for i, p in enumerate(def_ids)}
                result = SetSimulator(set_def, off, dfn, ctx=Context(), baseline=base, params=params, seed=SEED).simulate(ITERATIONS)
                row[f"{name}_ppp"] = result["ppp"]
                row[f"{name}_to"] = result["turnover_rate"]
            rows.append(row)
    d = pd.DataFrame(rows)
    by_set = d.groupby("set")[["eski_ppp", "yeni_ppp", "eski_to", "yeni_to"]].mean().reset_index()
    summary = pd.DataFrame([{"ölçüm": "Ortalama PPP", "eski": d.eski_ppp.mean(), "yeni": d.yeni_ppp.mean()},
                            {"ölçüm": "PPP standart sapması (eşleşmeler arası)", "eski": d.eski_ppp.std(), "yeni": d.yeni_ppp.std()},
                            {"ölçüm": "Ortalama top kaybı", "eski": d.eski_to.mean(), "yeni": d.yeni_to.mean()}])
    corr = float(d.eski_ppp.corr(d.yeni_ppp))
    league = float(read("possessions").query("season == @SEASON").points.mean())
    text = "\n".join(["# Simülatör: eski ve yeni puanlar\n", f"{SEASON}, {len(d)} set-eşleşme, her biri {ITERATIONS} tekrar. Kadrolar: en çok dakika alan beşli.\n",
                      table(summary), "", f"Eski-yeni PPP korelasyonu: {corr:.3f}. Ligin gerçek hücum başına sayısı: {league:.3f} (setler yalnızca set hücumunu temsil eder).\n",
                      "## Setlere göre\n", table(by_set), ""])
    (AUDIT_DIR / "sim_compare.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
