"""Stage 6 audit: clutch, game load, consistency and the single-game rating.

    uv run python scripts/audit/stage6.py

Read-only: writes only under data/audit/. E2026 takes no part in choosing parameters. Two rules
were fixed before running: clutch stops being a skill rating if the split-half correlation is
under 0.2, and plus/minus joins the game rating only if it predicts the next game better.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from foundation import table  # noqa: E402
from stage3 import K_GRID, REF, first_half_games, gain, rates, split_r, team_share  # noqa: E402

from bk.config import AUDIT_DIR, TABLES_DIR  # noqa: E402
from bk.ratings.mental import (MENTAL_ATTRIBUTES, MENTAL_SPECS, clutch_counts, consistency_counts, fit_spread_on_level,  # noqa: E402
                               game_rating_v2, load_counts, next_game_power, spread_table)
from bk.ratings.method import estimate_k, fixed_reference, score_fixed  # noqa: E402
from bk.ratings.metrics import game_score  # noqa: E402
from bk.ratings.metrics_v2 import Spec, league_level, load_tables, shrink  # noqa: E402

CLUTCH_GATE = 0.2
SEASON_MINUTES = 500
HALF_MINUTES = 200
CLUTCH_SPLIT_MIN_USE = 10
WEIGHTS = (0.0, 0.05, 0.1, 0.2)
BOOTSTRAP_ROUNDS = 100
PPP_RATIO = 1.11   # EuroLeague points per possession against the level game score was built on
WATCH = ["TAVARES", "CAMPAZZO", "DE COLO", "MICIC", "WALKUP", "LARKIN", "VEZENKOV", "PUNTER", "SLOUKAS", "BLATT"]


def group_counts(t, coefficients) -> dict:
    out = {**clutch_counts(t), **load_counts(t)}
    out["consistency_value"] = consistency_counts(t.player_games, coefficients)
    return out


def noise_of(metric: str, spec: Spec, mean: float) -> float:
    if spec.kind == "prop":
        return spec.dispersion * mean * (1 - mean)
    return spec.dispersion


def scale_scores(pg: pd.DataFrame, ppp_ratio: float) -> pd.Series:
    """Game score with the possession-linked weights scaled to the league's points per possession."""
    fgm, fga = pg.fg2m + pg.fg3m, pg.fg2a + pg.fg3a
    r = ppp_ratio
    return (pg.pts + 0.4 * fgm - 0.7 * r * fga - 0.4 * (pg.fta - pg.ftm) + 0.7 * r * pg.orb + 0.3 * r * pg.drb
            + r * pg.stl + 0.7 * pg.ast + 0.7 * r * pg.blk - 0.4 * pg.pf - r * pg.tov)


def bootstrap_difference(pg: pd.DataFrame, weight: float, rounds: int = BOOTSTRAP_ROUNDS) -> tuple[float, float]:
    """Change in next-game power from adding plus/minus, resampling player-seasons; returns mean and SD."""
    base, mixed = game_rating_v2(pg), game_rating_v2(pg, weight)
    base = base.assign(mixed_z=mixed.game_z)
    groups = {key: frame for key, frame in base.groupby(["season", "player_id"])}
    keys = list(groups)
    rng = np.random.default_rng(0)
    differences = []
    for _ in range(rounds):
        parts = []
        for i, pick in enumerate(rng.integers(0, len(keys), len(keys))):
            parts.append(groups[keys[pick]].assign(player_id=f"b{i}"))
        sample = pd.concat(parts, ignore_index=True)
        differences.append(next_game_power(sample, "mixed_z") - next_game_power(sample, "game_z"))
    return float(np.mean(differences)), float(np.std(differences))


def game_rating_table(t) -> pd.DataFrame:
    pg = t.player_games[t.player_games.season.isin(REF)]
    rows = []
    for w in WEIGHTS:
        g = game_rating_v2(pg, w)
        row = {"model": f"+/- ağırlığı %{100 * w:.0f}", "sonraki_maç_r": next_game_power(g),
               "E2024": next_game_power(g[g.season == "E2024"]), "E2025": next_game_power(g[g.season == "E2025"])}
        if w > 0:
            row["fark"], row["fark_sd"] = bootstrap_difference(pg, w)
        rows.append(row)
    base = game_rating_v2(pg)
    scaled = pg.assign(gmsc_scaled=scale_scores(pg, PPP_RATIO))
    z = pd.Series(0.0, index=scaled.index)
    for _, idx in scaled.groupby("season").groups.items():
        part = scaled.loc[idx]
        resid = part.gmsc_scaled - part.gmsc_scaled.sum() / part.minutes.sum() * part.minutes
        z.loc[idx] = resid / resid[part.minutes >= 10].std()
    with_scaled = base.assign(scaled_z=z.reindex(base.index))
    rows.append({"model": "Game score, lig hücum değerine ölçekli", "sonraki_maç_r": next_game_power(with_scaled, "scaled_z"),
                 "E2024": next_game_power(with_scaled[with_scaled.season == "E2024"], "scaled_z"),
                 "E2025": next_game_power(with_scaled[with_scaled.season == "E2025"], "scaled_z")})
    return pd.DataFrame(rows)


def main() -> None:
    t = load_tables()
    seasons = sorted(t.player_games.season.unique())
    coefficients = fit_spread_on_level([spread_table(t.window(x).player_games) for x in REF])
    full, split, minutes = {}, {}, {}
    for x in REF:
        w = t.window(x)
        first = first_half_games(w.player_games)
        rest = set(w.player_games.gamecode) - first
        full[x] = group_counts(w, coefficients)
        split[x] = (group_counts(t.window(x, first), coefficients), group_counts(t.window(x, rest), coefficients))
        minutes[x] = w.player_games.groupby("player_id").minutes.sum()
        minutes[(x, "h")] = tuple(w.player_games[w.player_games.gamecode.isin(g)].groupby("player_id").minutes.sum() for g in (first, rest))
    both = minutes["E2024"][minutes["E2024"] >= SEASON_MINUTES].index.intersection(minutes["E2025"][minutes["E2025"] >= SEASON_MINUTES].index)

    rows = []
    for metric, spec in MENTAL_SPECS.items():
        x_all, n_all = [], []
        for season in REF:
            r = rates(full[season][metric])
            x_all.append(r)
            n_all.append(full[season][metric][1].reindex(r.index))
        x_c, n_c = pd.concat(x_all).to_numpy(float), pd.concat(n_all).to_numpy(float)
        mean = float((x_c * n_c).sum() / n_c.sum())
        k_moment = estimate_k(x_c, n_c, noise_of(metric, spec, mean))

        def make(k: float) -> Spec:
            return Spec(spec.kind, k, dispersion=spec.dispersion)

        grid = (0.5, 1, 2, 4, 8, 16) + K_GRID if metric in ("load_minutes", "consistency_value") else K_GRID
        gains = {k: float(np.mean([gain(make(k), split[s][0][metric], split[s][1][metric]) for s in REF])) for k in grid}
        best = max(gains, key=gains.get)
        ahead = {k: gain(make(k), full["E2024"][metric], full["E2025"][metric]) for k in grid}
        best_a = max(ahead, key=ahead.get)
        rs = []
        for season in REF:
            a, b = minutes[(season, "h")]
            players = a[a >= HALF_MINUTES].index.intersection(b[b >= HALF_MINUTES].index)
            if metric == "clutch_value":
                n1, n2 = split[season][0][metric][1], split[season][1][metric][1]
                players = n1[n1 >= CLUTCH_SPLIT_MIN_USE].index.intersection(n2[n2 >= CLUTCH_SPLIT_MIN_USE].index)
            rs.append(split_r(rates(split[season][0][metric]), rates(split[season][1][metric]), players))
        pool = both
        if metric == "clutch_value":
            n1, n2 = full["E2024"][metric][1], full["E2025"][metric][1]
            pool = n1[n1 >= 2 * CLUTCH_SPLIT_MIN_USE].index.intersection(n2[n2 >= 2 * CLUTCH_SPLIT_MIN_USE].index)
        rows.append({"metrik": metric, "k_moment": round(k_moment, 1) if np.isfinite(k_moment) else "sonsuz", "yarı_en_iyi_k": best,
                     "yarı_kazanç": gains[best], "sezon_en_iyi_k": best_a, "sezon_kazanç": ahead[best_a], "yarı_r": float(np.mean(rs)),
                     "sezon_r": split_r(rates(full["E2024"][metric]), rates(full["E2025"][metric]), pool), "sezon_oyuncu": len(pool),
                     "koddaki_k": spec.k})
    params = pd.DataFrame(rows)
    params.to_csv(AUDIT_DIR / "stage6_params.csv", index=False)
    games = game_rating_table(t)
    typical_spread = pd.concat([spread_table(t.window(x).player_games) for x in REF])
    typical_spread = typical_spread[typical_spread.n >= 15].spread.median()

    # ratings on the fixed scale ----------------------------------------------------------------
    frames = []
    for i, x in enumerate(seasons):
        w = t.window(x)
        c = group_counts(w, coefficients)
        meta = w.player_games.groupby("player_id").agg(player=("player", "last"), team=("team", "last"), minutes=("minutes", "sum"), games=("gamecode", "size"))
        m = meta.assign(season=x)
        for metric, spec in MENTAL_SPECS.items():
            s, n = c[metric]
            level = league_level(s, n)
            theta, total, se = shrink(s, n, spec, level, index=m.index)
            m[metric], m[f"n_{metric}"], m[f"se_{metric}"] = theta, total, se
        m["clutch_points"] = c["clutch_points"][0].reindex(m.index).fillna(0)
        m["clutch_use"] = c["clutch_points"][1].reindex(m.index).fillna(0)
        frames.append(m.reset_index())
    metrics = pd.concat(frames, ignore_index=True)
    metrics["clutch_ppp"] = metrics.clutch_points / metrics.clutch_use.replace(0, np.nan)
    reference = fixed_reference(metrics)
    prior_k = {m: s.k for m, s in MENTAL_SPECS.items()}
    scored = pd.concat([score_fixed(g.set_index("player_id"), reference, MENTAL_ATTRIBUTES, prior_k).assign(season=x).reset_index()
                        for x, g in metrics.groupby("season")], ignore_index=True)
    ratings = pd.read_parquet(TABLES_DIR / "ratings_season_v1.parquet")[["season", "player_id", "qualified", "stamina", "consistency"]]
    j = metrics.merge(ratings, on=["season", "player_id"], suffixes=("", "_old")).merge(scored, on=["season", "player_id"], suffixes=("_old", ""))
    j.to_csv(AUDIT_DIR / "stage6_ratings.csv", index=False)

    f = j[j.season.isin(REF) & (j.minutes >= SEASON_MINUTES)]
    pv = {k: f.pivot(index="player_id", columns="season", values=k).reindex(both) for k in ("stamina", "consistency", "stamina_old", "consistency_old")}
    q25, q26 = j[(j.season == "E2025") & j.qualified], j[(j.season == "E2026") & j.qualified]
    summary = pd.DataFrame([{
        "özellik": k, "sezon_r_eski": pv[f"{k}_old"].E2024.corr(pv[f"{k}_old"].E2025), "sezon_r_yeni": pv[k].E2024.corr(pv[k].E2025),
        "eski_yeni_r": f[f"{k}_old"].corr(f[k]), "takım_payı_eski": team_share(f, f"{k}_old"), "takım_payı_yeni": team_share(f, k),
        "aralık_E25": (q25[f"{k}_hi"] - q25[f"{k}_lo"]).mean(), "aralık_E26": (q26[f"{k}_hi"] - q26[f"{k}_lo"]).mean(),
        "az_veri_E25": q25[f"{k}_low_data"].mean(), "az_veri_E26": q26[f"{k}_low_data"].mean()} for k in ("stamina", "consistency")])

    means = j[j.qualified].groupby("season").consistency.mean().round(1).to_dict()
    out = ["# Aşama 6: Clutch, Oyun Yükü, İstikrar, maç puanı\n", "Üretim puanları değişmedi.\n",
           f"İstikrar ortalaması sezona göre (kısa sezon önyargısı kontrolü): {means}.\n", "## 1. Metrikler\n", table(params), "",
           f"Clutch kuralı: yarı_r {CLUTCH_GATE} altındaysa beceri puanı olmaz. Yarı başına en az {CLUTCH_SPLIT_MIN_USE} clutch hücum.\n",
           "## 2. Puanlar\n", table(summary), "", "## 3. Maç puanı: sonraki maçı tahmin\n",
           "Bir maçın değeri ile oyuncunun sonraki maçtaki üretimi arasındaki korelasyon; oyuncunun seviyesi bu iki maç dışarıda "
           "bırakılarak hesaplanır. `fark`: +/- eklemenin etkisi, `fark_sd`: oyuncu örneklemesiyle belirsizliği. Kural: +/- ancak bunu iyileştirirse eklenir.\n", table(games), "",
           f"Tipik dalgalanma (medyan, en az 15 maç): {typical_spread:.1f}.\n",
           "## 4. E2025 (en az 500 dakika)\n"]
    e = j[(j.season == "E2025") & (j.minutes >= SEASON_MINUTES)]
    for k in ("stamina", "consistency"):
        order = e.sort_values([k, f"{k}_old"], ascending=False)
        fmt = lambda d: ", ".join(f"{r.player.title()} {getattr(r, k)} ({getattr(r, k + '_old')})" for r in d.itertuples())  # noqa: E731
        out += [f"**{k}**", f"- Üst: {fmt(order.head(8))}", f"- Alt: {fmt(order.tail(6))}", ""]
    clutch_table = e[e.clutch_use >= 25].sort_values("clutch_ppp", ascending=False)
    out += ["**Bu sezon clutch performansı (en az 25 clutch hücum):**\n",
            table(pd.concat([clutch_table.head(6), clutch_table.tail(4)])[["player", "team", "clutch_points", "clutch_use", "clutch_ppp", "clutch_value"]]), "",
            "## 5. İzlenen oyuncular (E2026)\n"]
    w = j[(j.season == "E2026") & j.player.str.contains("|".join(WATCH), case=False)]
    out += [table(w[["player", "minutes", "stamina_old", "stamina", "stamina_lo", "stamina_hi", "consistency_old", "consistency", "consistency_lo", "consistency_hi", "consistency_low_data"]]), ""]
    text = "\n".join(out)
    (AUDIT_DIR / "stage6.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
