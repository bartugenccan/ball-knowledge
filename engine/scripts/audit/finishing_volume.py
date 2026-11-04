"""Finishing with volume: parameter choice, old and new ratings, and the interval check.

    uv run python scripts/audit/finishing_volume.py

Read-only: writes only under data/audit/. The weights are a product decision made after seeing
E2026 results, so E2026 is no longer an independent test of this attribute.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from foundation import table  # noqa: E402
from stage3 import CARRY_GRID, K_GRID, MIN_IMPROVEMENT, REF, SEASON_MINUTES, first_half_games, gain, rates, split_r, team_share  # noqa: E402

from bk.config import AUDIT_DIR  # noqa: E402
from bk.ratings.attributes import Attribute  # noqa: E402
from bk.ratings.method import Z_INTERVAL, fixed_reference, score_fixed  # noqa: E402
from bk.ratings.metrics_v2 import ATTRIBUTES_V2, SPECS, Spec, counts, fit_role, league_level, load_tables, role_offset, season_metrics, shrink  # noqa: E402

METRICS = ("inside_rate", "inside_self_rate")
SMALL_K = (2, 5, 10, 15, 20, 30)
LOW_MINUTES, LOW_FGA = 100, 2.5
LOW_FIRST_HALF_ATTEMPTS, HIGH_PCT, MIN_SECOND_HALF = 40, 0.70, 5
COVERAGE_FLOOR = 0.70
WATCH = ["JONES, KAI", "HALL, DONTA", "TAVARES", "OTURU", "KABENGELE", "VEZENKOV", "LESSORT", "MILUTINOV", "NEBO", "DOKOSSI", "BLATT", "CAMPAZZO"]


def selection(full: dict, split: dict) -> pd.DataFrame:
    rows = []
    for metric in METRICS:
        spec = SPECS[metric]

        def make(k: float) -> Spec:
            return Spec(spec.kind, k, scale=spec.scale)

        grid = SMALL_K + K_GRID
        both = {k: float(np.mean([gain(make(k), split[x][0][metric], split[x][1][metric]) for x in REF])) for k in grid}
        past = (*full["E2024"][metric], league_level(*full["E2024"][metric]))
        first, second = split["E2025"][0][metric], split["E2025"][1][metric]

        def run(k: float, w: float) -> float:
            return gain(make(k), first, second, None, [(*past, w)] if w > 0 else None)

        by_w = {w: max(run(k, w) for k in grid) for w in CARRY_GRID}
        best_w = max(by_w, key=by_w.get)
        use_w = best_w if by_w[best_w] - by_w[0.0] >= MIN_IMPROVEMENT else 0.0
        results = {k: run(k, use_w) for k in grid}
        best_k = max(results, key=results.get)
        rows.append({"metrik": metric, "iki_sezon_k": max(both, key=both.get), "iki_sezon_kazanç": max(both.values()), "E25_geçmişsiz": by_w[0.0],
                     "E25_geçmişli": by_w[best_w], "kurala_göre_w": use_w, "kurala_göre_k": best_k, "kazanç": results[best_k],
                     "koddaki": f"k={spec.k:g} w={spec.carry:g}"})
    return pd.DataFrame(rows)


def low_volume_coverage(t, full: dict, split: dict) -> pd.DataFrame:
    """Do 80% intervals hold for few attempts at a high rate, the group the attribute got wrong?"""
    spec = SPECS["inside_adj"]
    rows = []
    for factor in (1.0, 1.25, 1.5, 2.0, 3.0):
        hits = total = 0
        for season, other in (("E2024", "E2025"), ("E2025", "E2024")):
            s1, n1 = split[season][0]["inside_adj"]
            s2, n2 = split[season][1]["inside_adj"]
            attempts = n1.reindex(n2.index).fillna(0)
            raw = (s1.reindex(n2.index).fillna(0) / attempts.replace(0, np.nan))
            test = n2.index[(attempts <= LOW_FIRST_HALF_ATTEMPTS) & (attempts >= 10) & (raw >= HIGH_PCT) & (n2 >= MIN_SECOND_HALF)]
            level = league_level(s1, n1)
            beta = fit_role([(*full[other]["inside_adj"], league_level(*full[other]["inside_adj"]), t.window(other).people)])
            offset = role_offset(test, n1, t.window(season).people, beta)
            past = [(*full["E2024"]["inside_adj"], league_level(*full["E2024"]["inside_adj"]), spec.carry)] if season == "E2025" else None
            scaled = Spec(spec.kind, spec.k, dispersion=spec.dispersion * factor)
            theta, _, se = shrink(s1, n1, scaled, level, offset, past, test)
            x2 = s2.reindex(test).fillna(0) / n2.reindex(test)
            spread = np.sqrt(scaled.dispersion * theta * (1 - theta) / n2.reindex(test) + se**2)
            hits += int(((x2 - theta).abs() <= Z_INTERVAL * spread).sum())
            total += len(test)
        rows.append({"varyans_çarpanı": factor, "oyuncu": total, "kapsama": hits / max(total, 1)})
    return pd.DataFrame(rows)


def main() -> None:
    t = load_tables()
    full, split, minutes = {}, {}, {}
    for x in REF:
        w = t.window(x)
        first = first_half_games(w.player_games)
        rest = set(w.player_games.gamecode) - first
        full[x] = counts(w)
        split[x] = (counts(t.window(x, first)), counts(t.window(x, rest)))
        a = w.player_games[w.player_games.gamecode.isin(first)].groupby("player_id").minutes.sum()
        b = w.player_games[w.player_games.gamecode.isin(rest)].groupby("player_id").minutes.sum()
        minutes[x] = a[a >= 200].index.intersection(b[b >= 200].index)
    chosen = selection(full, split)
    coverage = low_volume_coverage(t, full, split)
    reliability = pd.DataFrame([{"metrik": m, "yarı_r": float(np.mean([split_r(rates(split[x][0][m]), rates(split[x][1][m]), minutes[x]) for x in REF]))}
                                for m in ("inside_adj", *METRICS)])

    metrics = season_metrics(t)
    reference = fixed_reference(metrics)
    finishing = next(a for a in ATTRIBUTES_V2 if a.key == "finishing")
    accuracy_only = Attribute("finishing_old", "", "hucum", "turetilmis", (("inside_adj", 1, 1),))
    prior_k = {m: SPECS[m].k for m in ("inside_adj", *METRICS)}
    scored = pd.concat([score_fixed(g.set_index("player_id"), reference, (finishing, accuracy_only), prior_k).assign(season=x).reset_index()
                        for x, g in metrics.groupby("season")], ignore_index=True)
    inside = t.shots[t.shots.zone_group == "inside"].groupby(["season", "player_id"]).agg(fga=("made", "size"), fgm=("made", "sum"), ast=("assisted", "sum")).reset_index()
    box = t.player_games.groupby(["season", "player_id"]).pts.sum().rename("pts").reset_index()
    j = metrics[["season", "player_id", "player", "team", "games", "minutes", "inside_rate", "inside_self_rate"]].merge(scored, on=["season", "player_id"]).merge(inside, how="left").merge(box)
    j["ppg"], j["fga_g"], j["pct"], j["ast_share"] = j.pts / j.games, j.fga.fillna(0) / j.games, j.fgm / j.fga, j.ast / j.fgm.replace(0, np.nan)
    j.to_csv(AUDIT_DIR / "finishing_volume.csv", index=False)

    f = j[j.season.isin(REF) & (j.minutes >= SEASON_MINUTES)]
    both = f.groupby("player_id").season.nunique()
    both = both[both == 2].index
    low = j[(j.minutes >= LOW_MINUTES) & (j.fga_g <= LOW_FGA)]
    rows = []
    for name, k in (("Yalnız isabet (eski)", "finishing_old"), ("%40 isabet, %40 hacim, %20 kendi yarattığı", "finishing")):
        pv = f.pivot(index="player_id", columns="season", values=k).reindex(both)
        rows.append({"model": name, "sezon_r": pv.E2024.corr(pv.E2025), "asist_payı_r": f[k].corr(f.ast_share), "sayı_ort_r": f[k].corr(f.ppg),
                     "takım_payı": team_share(f, k), "düşük_hacim_en_yüksek": int(low[k].max()), "düşük_hacim_17+": int((low[k] >= 17).sum()),
                     "düşük_hacim_oyuncu": len(low)})
    compare = pd.DataFrame(rows)
    bands = f.assign(bant=pd.cut(f.fga_g, [0, 1.5, 2.5, 3.5, 5, 20])).groupby("bant", observed=True).agg(
        oyuncu=("finishing", "size"), eski=("finishing_old", "mean"), yeni=("finishing", "mean"), yeni_max=("finishing", "max"), isabet=("pct", "mean"), sayı=("ppg", "mean")).reset_index()
    bands["bant"] = bands.bant.astype(str)

    def listing(season: str, key: str, n: int) -> str:
        e = j[(j.season == season) & (j.minutes >= (SEASON_MINUTES if season != "E2026" else 100))].sort_values([key, "fga"], ascending=False)
        return ", ".join(f"{r.player.title()} {getattr(r, key)}" for r in e.head(n).itertuples())

    watch = j[j.player.str.contains("|".join(WATCH), case=False) & j.season.isin(["E2025", "E2026"]) & (j.minutes >= 100)].sort_values(["player", "season"])
    moves = f[f.season == "E2025"].assign(fark=lambda d: d.finishing - d.finishing_old)
    moves = moves.reindex(moves.fark.abs().sort_values(ascending=False).index).head(12)
    text = "\n".join([
        "# Bitiricilik: hacim ve kendi yaratılan isabet\n",
        "Ağırlıklar ürün kararıdır ve E2026 sonuçları görülerek seçildi; bu özellik için E2026 artık bağımsız test değildir. Bağımsız kontrol, tablolara girecek yeni maçlardır.\n",
        "## 1. Hacim metrikleri için parametreler\n", "Rol beklentisi bilinçli olarak yok: pivotun düşük hacmini yukarı çekmemeli.\n", table(chosen), "", table(reliability), "",
        "## 2. Model karşılaştırması\n", f"`düşük hacim`: en az {LOW_MINUTES} dk, maç başı en fazla {LOW_FGA} deneme.\n", table(compare), "",
        "## 3. Maç başı deneme bandına göre (500+ dk, E2024-E2025)\n", table(bands), "",
        "## 4. Aralık kontrolü: az deneme, yüksek isabet\n", f"İlk yarıda 10-{LOW_FIRST_HALF_ATTEMPTS} deneme ve en az %{100 * HIGH_PCT:.0f} isabet; hedef %80 kapsama, alt sınır %{100 * COVERAGE_FLOOR:.0f}.\n", table(coverage), "",
        "## 5. Sıralamalar\n", "**E2025, en az 500 dk:** " + listing("E2025", "finishing", 12), "", "**E2026, en az 100 dk:** " + listing("E2026", "finishing", 12), "",
        "**En çok değişenler (E2025):**\n", table(moves[["player", "team", "ppg", "fga_g", "pct", "ast_share", "finishing_old", "finishing", "fark"]]), "",
        "## 6. İzlenen oyuncular\n", table(watch[["season", "player", "ppg", "fga", "fga_g", "pct", "ast_share", "finishing_old", "finishing", "finishing_lo", "finishing_hi", "finishing_low_data"]]), "",
    ])
    (AUDIT_DIR / "finishing_volume.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
