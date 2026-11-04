"""Stage 3 audit: new formulas for the lower-risk attributes, next to the current ratings.

    uv run python scripts/audit/stage3.py

Read-only: writes only under data/audit/. Parameters are chosen on the second half of E2024
and E2025; E2026 is held back as the final check of the whole project.

Selection rule, fixed before looking at results: a role prior or past-season counts are used
only when they improve the E2025 out-of-sample gain by at least MIN_IMPROVEMENT points.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from foundation import table  # noqa: E402
from method import halves as _unused  # noqa: E402,F401
from method import window_counts  # noqa: E402

from bk.config import AUDIT_DIR, TABLES_DIR  # noqa: E402
from bk.ratings.method import Z_INTERVAL, estimate_k  # noqa: E402
from bk.ratings.metrics import WindowData, league_priors, shooter_expectation  # noqa: E402
from bk.ratings.metrics_v2 import (ATTRIBUTES_V2, SPECS, Spec, Tables, counts, fit_role, league_level,  # noqa: E402
                                   load_tables, role_offset, score_frames, season_metrics, shrink)

K_GRID = (5, 10, 20, 40, 60, 80, 120, 150, 200, 300, 400, 600, 800, 1000, 1500, 2000, 4000, 8000)
CARRY_GRID = (0.0, 0.25, 0.5, 1.0)
MIN_IMPROVEMENT = 0.5
REF = ("E2024", "E2025")
HALF_MINUTES = 200       # both halves, for split-half correlations
SEASON_MINUTES = 500     # both seasons, for year-to-year correlations
COVERAGE_MIN_TRIALS = 30
OLD_METRIC = {"free_throw": "ft_pct", "steals": "stl_rate", "shot_blocking": "blk_rate", "discipline": "pf_rate",
              "off_rebounding": "orb_rate", "def_rebounding": "drb_rate", "ball_security": "tov_pct",
              "drawing_fouls": "ftr", "shot_creation": "unast_rate", "passing": "ast_rate"}
STAGE_METRICS = {"ft_pct", "stl_rate", "blk_share", "foul_rate", "orb_share", "drb_share", "tov_share", "fd_rate", "trip_rate",
                 "creation_rate", "ast_share", "created_rate"}
WATCH = ["TAVARES", "CAMPAZZO", "CROWDER", "LARKIN", "LESSORT", "FRANCISCO", "JAMES, MIKE", "VEZENKOV", "MILUTINOV"]


def first_half_games(player_games: pd.DataFrame) -> set:
    dates = player_games.groupby("gamecode").date.first().sort_values()
    return set(dates.index[: len(dates) // 2])


def weighted_mse(pred: pd.Series, x: pd.Series, n: pd.Series) -> float:
    return float((n * (x - pred) ** 2).sum() / n.sum())


def gain(spec: Spec, first: tuple, second: tuple, offset=None, past=None) -> float:
    """% less squared error than the league average when predicting the second half."""
    s1, n1 = first
    s2, n2 = second
    test = n2[n2 > 0].index
    level = league_level(s1, n1)
    theta, _, _ = shrink(s1, n1, spec, level, offset, past, test)
    x2 = s2.reindex(test).fillna(0) / n2.reindex(test)
    w = n2.reindex(test)
    return 100 * (1 - weighted_mse(theta, x2, w) / weighted_mse(pd.Series(level, index=test), x2, w))


def coverage(spec: Spec, first: tuple, second: tuple, offset, past) -> float:
    """Share of second-half results inside the 80% predictive interval (players with >= 30 trials)."""
    s1, n1 = first
    s2, n2 = second
    test = n2[n2 >= COVERAGE_MIN_TRIALS].index
    level = league_level(s1, n1)
    theta, _, se = shrink(s1, n1, spec, level, offset, past, test)
    x2 = s2.reindex(test).fillna(0) / n2.reindex(test)
    variance = theta * (1 - theta) if spec.kind == "prop" else theta
    spread = np.sqrt(spec.dispersion * variance.clip(lower=1e-9) / n2.reindex(test) + se**2)
    return float(((x2 - theta).abs() <= Z_INTERVAL * spread).mean())


def split_r(a1: pd.Series, a2: pd.Series, players: pd.Index) -> float:
    return float(a1.reindex(players).corr(a2.reindex(players)))


def rates(c: tuple) -> pd.Series:
    s, n = c
    has = n[n > 0].index
    return s.reindex(has).fillna(0) / n.reindex(has)


def selection_table(t: Tables, full: dict, split: dict) -> pd.DataFrame:
    rows = []
    for metric, spec in SPECS.items():
        if metric not in STAGE_METRICS:
            continue
        x_all, n_all = [], []
        for season in REF:
            r = rates(full[season][metric])
            x_all.append(r)
            n_all.append(full[season][metric][1].reindex(r.index))
        x_c, n_c = pd.concat(x_all).to_numpy(float), pd.concat(n_all).to_numpy(float)
        mean = float((x_c * n_c).sum() / n_c.sum())
        noise = spec.dispersion * (mean * (1 - mean) if spec.kind == "prop" else mean)
        k_moment = estimate_k(x_c, n_c, noise)

        def make(k: float) -> Spec:
            return Spec(spec.kind, k, dispersion=spec.dispersion, scale=spec.scale)

        both = {k: np.mean([gain(make(k), split[s][0][metric], split[s][1][metric]) for s in REF]) for k in K_GRID}
        k_test = max(both, key=both.get)

        first25, second25 = split["E2025"][0][metric], split["E2025"][1][metric]
        people25 = t.window("E2025").people
        beta = fit_role([(*full["E2024"][metric], league_level(*full["E2024"][metric]), t.window("E2024").people)])
        test = second25[1][second25[1] > 0].index
        offset = role_offset(test, first25[1], people25, beta)
        past24 = (*full["E2024"][metric], league_level(*full["E2024"][metric]))

        def run(k: float, role: bool, w: float) -> float:
            past = [(*past24, w)] if w > 0 else None
            return gain(make(k), first25, second25, offset if role else None, past)

        plain = max(run(k, False, 0) for k in K_GRID)
        with_role = max(run(k, True, 0) for k in K_GRID)
        with_carry = {w: max(run(k, False, w) for k in K_GRID) for w in CARRY_GRID}
        use_role = with_role - plain >= MIN_IMPROVEMENT
        grid = {w: max(run(k, use_role, w) for k in K_GRID) for w in CARRY_GRID}
        base = grid[0.0]
        best_w = max(grid, key=grid.get)
        use_w = best_w if grid[best_w] - base >= MIN_IMPROVEMENT else 0.0
        results = {k: run(k, use_role, use_w) for k in K_GRID}
        final_k = max(results, key=results.get)
        cover = coverage(make(final_k), first25, second25, offset if use_role else None,
                         [(*past24, use_w)] if use_w > 0 else None)
        rows.append({"metrik": metric, "k_moment": round(k_moment) if np.isfinite(k_moment) else "sonsuz",
                     "k_test": k_test, "iki_sezon_kazanç": both[k_test], "E25_yalın": plain, "E25_rol": with_role,
                     "E25_geçmiş": max(with_carry.values()), "seçilen_k": final_k, "seçilen_rol": use_role,
                     "seçilen_w": use_w, "seçilen_kazanç": results[final_k], "aralık_kapsama": cover,
                     "koddaki": f"k={spec.k:g} rol={spec.role} w={spec.carry:g}"})
    return pd.DataFrame(rows)


def old_vs_new(t: Tables, full: dict, split: dict, old_full: dict, old_split: dict, minutes: dict) -> pd.DataFrame:
    rows = []
    both_seasons = minutes["E2024"][minutes["E2024"] >= SEASON_MINUTES].index.intersection(
        minutes["E2025"][minutes["E2025"] >= SEASON_MINUTES].index)
    for a in ATTRIBUTES_V2:
        if a.key not in OLD_METRIC:
            continue
        old = OLD_METRIC[a.key]
        for metric, _, _ in a.components:
            def corr_split(store, name):
                rs = []
                for season in REF:
                    half = minutes[(season, "halves")]
                    players = half[0][half[0] >= HALF_MINUTES].index.intersection(half[1][half[1] >= HALF_MINUTES].index)
                    rs.append(split_r(rates(store[season][0][name][:2]), rates(store[season][1][name][:2]), players))
                return float(np.mean(rs))

            rows.append({"özellik": a.key, "yeni_metrik": metric, "yarı_r_eski": corr_split(old_split, old),
                         "yarı_r_yeni": corr_split(split, metric),
                         "sezon_r_eski": split_r(rates(old_full["E2024"][old][:2]), rates(old_full["E2025"][old][:2]), both_seasons),
                         "sezon_r_yeni": split_r(rates(full["E2024"][metric]), rates(full["E2025"][metric]), both_seasons)})
    return pd.DataFrame(rows)


def team_share(d: pd.DataFrame, col: str) -> float:
    out = []
    for _, g in d.groupby("season"):
        grand = g[col].mean()
        between = g.groupby("team")[col].apply(lambda x: len(x) * (x.mean() - grand) ** 2).sum()
        out.append(between / ((g[col] - grand) ** 2).sum())
    return float(np.mean(out))


def main() -> None:
    t = load_tables()
    full = {x: counts(t.window(x)) for x in REF}
    split, old_full, old_split, minutes = {}, {}, {}, {}
    for x in REF:
        w = t.window(x)
        first = first_half_games(w.player_games)
        rest = set(w.player_games.gamecode) - first
        split[x] = (counts(t.window(x, first)), counts(t.window(x, rest)))
        minutes[x] = w.player_games.groupby("player_id").minutes.sum()
        minutes[(x, "halves")] = tuple(w.player_games[w.player_games.gamecode.isin(g)].groupby("player_id").minutes.sum()
                                       for g in (first, rest))

        def old_counts(games: set | None) -> dict:
            win = t.window(x, games)
            shots = win.shots.copy()
            shots["resid"] = shots.made.astype(float) - shooter_expectation(
                shots, league_priors(WindowData(shots, win.player_games, win.possessions)))
            return window_counts(WindowData(shots, win.player_games, win.possessions))

        old_full[x] = old_counts(None)
        old_split[x] = (old_counts(first), old_counts(rest))

    selection = selection_table(t, full, split)
    selection.to_csv(AUDIT_DIR / "stage3_selection.csv", index=False)
    measures = old_vs_new(t, full, split, old_full, old_split, minutes)

    # team rebounds: chances with or without them
    alt = {x: tuple(counts(t.window(x, g), team_rebounds_count=True)
                    for g in (first_half_games(t.window(x).player_games),
                              set(t.window(x).player_games.gamecode) - first_half_games(t.window(x).player_games))) for x in REF}
    reb_rows = []
    for metric in ("orb_share", "drb_share"):
        for name, store in (("yalnız oyuncu ribaundu", split), ("takım ribaundu dahil", alt)):
            g = [max(gain(Spec("prop", k), store[x][0][metric], store[x][1][metric]) for k in K_GRID) for x in REF]
            reb_rows.append({"metrik": metric, "payda": name, "kazanç": float(np.mean(g))})

    metrics = season_metrics(t)
    new = score_frames(metrics)
    ratings = pd.read_parquet(TABLES_DIR / "ratings_season_v1.parquet")
    keys = [a.key for a in ATTRIBUTES_V2 if a.key in OLD_METRIC]
    j = ratings[["season", "player_id", "player", "team", "games", "minutes", "qualified"] + keys].merge(
        new, on=["season", "player_id"], suffixes=("_old", ""))
    long_rows = [j[["season", "player_id", "player", "team", "games", "minutes", "qualified"]].assign(
        attribute=k, old=j[f"{k}_old"], new=j[k], lo=j[f"{k}_lo"], hi=j[f"{k}_hi"], low_data=j[f"{k}_low_data"]) for k in keys]
    pd.concat(long_rows).to_csv(AUDIT_DIR / "stage3_ratings.csv", index=False)

    full_seasons = j[(j.season.isin(REF)) & (j.minutes >= SEASON_MINUTES)]
    teams = full_seasons.groupby("season").team.nunique().mean()
    baseline = float((teams - 1) / (len(full_seasons) / 2 - 1))
    q26 = j[(j.season == "E2026") & j.qualified]
    q25 = j[(j.season == "E2025") & j.qualified]
    summary = pd.DataFrame([{
        "özellik": k, "eski_yeni_r": full_seasons[f"{k}_old"].corr(full_seasons[k]),
        "3+_değişen_%": 100 * ((full_seasons[f"{k}_old"] - full_seasons[k]).abs() >= 3).mean(),
        "takım_payı_eski": team_share(full_seasons, f"{k}_old"), "takım_payı_yeni": team_share(full_seasons, k),
        "aralık_E25": (q25[f"{k}_hi"] - q25[f"{k}_lo"]).mean(), "aralık_E26": (q26[f"{k}_hi"] - q26[f"{k}_lo"]).mean(),
        "az_veri_E25": q25[f"{k}_low_data"].mean(), "az_veri_E26": q26[f"{k}_low_data"].mean(),
        "18+_E26_eski": int((q26[f"{k}_old"] >= 18).sum()), "18+_E26_yeni": int((q26[k] >= 18).sum())} for k in keys])

    out = ["# Aşama 3: Düşük riskli özellikler\n",
           "Üretim puanları değişmedi. Tanımlar için `engine/bk/ratings/metrics_v2.py`.\n",
           "## 1. Parametre seçimi\n",
           f"Kazanç: ilk yarıdan ikinci yarıyı tahminde lig ortalamasına göre hata azalması (%). Rol ve geçmiş yalnızca "
           f"E2025 kazancını en az {MIN_IMPROVEMENT} puan artırırsa seçilir.\n", table(selection), "",
           "**Ribaund paydası:**\n", table(pd.DataFrame(reb_rows)), "",
           "## 2. Eski ve yeni tanım\n",
           f"`yarı_r`: iki yarı arası korelasyon, her yarıda en az {HALF_MINUTES} dakika. `sezon_r`: E2024-E2025 ham korelasyon, "
           f"her sezon en az {SEASON_MINUTES} dakika. Geçmiş sezon verisi kapalı.\n", table(measures), "",
           "## 3. Puan karşılaştırması\n",
           f"En az {SEASON_MINUTES} dakikalık E2024-E2025 oyuncu-sezonları. Takım payı için gürültü düzeyi yaklaşık {baseline:.2f}.\n",
           table(summary), "", "## 4. E2025 en yüksek ve en düşük 5 (en az 500 dakika)\n"]
    e25 = j[(j.season == "E2025") & (j.minutes >= SEASON_MINUTES)]
    for k in keys:
        order = e25.sort_values([k, f"{k}_old"], ascending=False)
        fmt = lambda d: ", ".join(f"{r.player.title()} {getattr(r, k)} ({getattr(r, k + '_old')})" for r in d.itertuples())  # noqa: E731
        out += [f"**{k}**", f"- Üst: {fmt(order.head(5))}", f"- Alt: {fmt(order.tail(5))}", ""]
    out += ["Parantez içi eski puan.\n", "## 5. En çok değişenler (E2025, en az 500 dakika)\n"]
    moves = []
    for k in keys:
        d = e25.assign(fark=e25[k] - e25[f"{k}_old"], attr=k, eski=e25[f"{k}_old"], yeni=e25[k])
        moves.append(d.reindex(d.fark.abs().sort_values(ascending=False).index).head(3)[["attr", "player", "team", "eski", "yeni", "fark"]])
    out += [table(pd.concat(moves)), "", "## 6. İzlenen oyuncular (E2026)\n"]
    watch = j[(j.season == "E2026") & j.player.str.contains("|".join(WATCH), case=False)]
    columns = ["player", "minutes"] + [c for k in keys[:6] for c in (f"{k}_old", k)]
    out += [table(watch[columns]), "", "Tüm oyuncular: `stage3_ratings.csv`.\n"]
    text = "\n".join(out)
    (AUDIT_DIR / "stage3.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
