"""Which three-point formula says the most about next season? Compares weightings and value equations.

    uv run python scripts/audit/three_value.py

Value equations multiply attempts per game by the make rate above a base. The chosen one, 3 x attempts
x (make rate - 0.32), is in bk.ratings.metrics_v2. Volume alone would win on "made threes next season",
so accuracy next season is the check against that, and low-volume shooters must not reach the top.

Writes data/audit/three_value.md.
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import pandas as pd  # noqa: E402

from bk.config import AUDIT_DIR, TABLES_DIR  # noqa: E402
from bk.ratings.attributes import Attribute  # noqa: E402
from bk.ratings.method import fixed_reference, score_fixed  # noqa: E402

BASES = (0.28, 0.30, 0.32, 0.34)
POWERS = (0.75, 1.0)
PAIRS = (("E2024", "E2025", 15, 20), ("E2025", "E2026", 5, 8))


def main() -> None:
    m = pd.read_parquet(TABLES_DIR / "player_metrics.parquet")
    pg = pd.read_parquet(TABLES_DIR / "player_games.parquet")
    box = pg[pg.minutes > 0].groupby(["season", "player_id"]).agg(g=("gamecode", "nunique"), made=("fg3m", "sum"), att=("fg3a", "sum")).reset_index()
    box["apg"], box["pct"] = box.att / box.g, box.made / box.att.clip(lower=1)
    m = m.merge(box[["season", "player_id", "apg"]], on=["season", "player_id"], how="left")
    reference = fixed_reference(m)

    def rate(column: str | None, weights=None) -> pd.DataFrame:
        parts = ((column, 1, 1),) if column else (("three_pct", weights[0], 1), ("three_rate", weights[1], 1))
        attribute = Attribute("x", "", "hucum", "turetilmis", parts)
        out = [score_fixed(g.set_index("player_id"), reference, (attribute,), {})["x"].rename("r").reset_index().assign(season=s) for s, g in m.groupby("season")]
        return pd.concat(out)

    candidates = {"%75 isabet, %25 hacim": rate(None, (0.75, 0.25)), "%60 isabet, %40 hacim": rate(None, (0.6, 0.4))}
    for base in BASES:
        for power in POWERS:
            m["candidate"] = m.apg.fillna(0) ** power * (m.three_pct - base)
            m["se_candidate"], m["n_candidate"] = 0.0, 999.0
            reference = fixed_reference(m)
            candidates[f"deneme^{power} x (isabet - {base:.2f})"] = rate("candidate")
    candidates["Seçilen: 3 x deneme x (isabet - 0.32)"] = pd.read_parquet(TABLES_DIR / "ratings_season.parquet")[["season", "player_id", "three_point"]].rename(columns={"three_point": "r"})

    rows = []
    for name, r in candidates.items():
        row = [name]
        for a, b, min_games, min_attempts in PAIRS:
            x = r[r.season == a].set_index("player_id").r
            y = box[(box.season == b) & (box.g >= min_games) & (box.att >= min_attempts)].set_index("player_id")
            i = x.index.intersection(y.index)
            row += [f"{x[i].rank().corr((y.made / y.g)[i].rank()):.3f}", f"{x[i].rank().corr(y.pct[i].rank()):.3f}"]
        d = r.merge(box, on=["season", "player_id"])
        low = d[(d.apg <= 3) & (d.att > 0)]
        row += [int((low[low.season == "E2025"].r >= 16).sum()), int((low[low.season == "E2026"].r >= 16).sum())]
        rows.append(row)
    header = ["Formül", "Sonraki isabetli üçlük (24→25)", "Sonraki yüzde (24→25)", "Sonraki isabetli üçlük (25→26)", "Sonraki yüzde (25→26)", "≤3 deneme, 16+ (E2025)", "≤3 deneme, 16+ (E2026)"]
    lines = ["# Üçlük puanı formülü", "", "Sıra korelasyonu. Hacim tek başına isabetli üçlüğü iyi öngörür, bu yüzden yüzde sütunu da okunmalı.", "",
             "| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    out = "\n".join(lines) + "\n"
    (AUDIT_DIR / "three_value.md").write_text(out, encoding="utf-8")
    print(out.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
