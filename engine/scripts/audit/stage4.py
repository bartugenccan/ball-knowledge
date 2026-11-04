"""Stage 4 audit: shooting attributes, next to the current ratings.

    uv run python scripts/audit/stage4.py

Read-only: writes only under data/audit/. Parameters follow the rule fixed in stage 3 and E2026
takes no part in choosing them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from foundation import table  # noqa: E402
from stage3 import (CARRY_GRID, K_GRID, MIN_IMPROVEMENT, REF, SEASON_MINUTES, coverage, first_half_games, gain,  # noqa: E402
                    rates, split_r, team_share)

from bk.config import AUDIT_DIR, TABLES_DIR  # noqa: E402
from bk.ratings.method import estimate_k  # noqa: E402
from bk.ratings.metrics_v2 import (ATTRIBUTES_V2, SPECS, Spec, counts, fit_role, ft_skill, league_level,  # noqa: E402
                                   load_tables, role_offset, score_frames, season_metrics, shrink)

STAGE_METRICS = ("three_pct", "three_rate", "mid_pct", "mid_rate", "inside_adj", "corner3_pct")
KEYS = ("three_point", "mid_range", "finishing")
HALF_MINUTES = 200
SEASON_AHEAD_MIN = 50   # attempts in both seasons
MIN_ARENA_ATTEMPTS = 40
MIN_SAME_PLAYER = 30
VOLUME_BANDS = [0, 1, 3, 5, 8, 100]   # attempts per 100 own possessions in the first half
GAME_BANDS = [-0.01, 0.5, 1, 2, 3, 4, 20]
WATCH = ["LEDAY", "BUTKEVICIUS", "BROOKS, ARMONI", "OBST", "TAVARES", "CROWDER", "ABALDE", "GIFFEY", "BEAUBOIS", "NEBO",
         "DE COLO", "LARKIN"]
OLD_STAGE = {"three_point": "three_pct", "mid_range": "mid_pct"}


def old_rates(t, games=None) -> dict[str, tuple[pd.Series, pd.Series]]:
    """Current definitions, raw: all threes, the mid zone, and the 0.7 rim + 0.3 paint blend."""
    s = t.shots
    out = {}
    for name, mask in (("three_pct", s.value == 3), ("mid_pct", s.zone == "mid"), ("rim", s.zone == "rim"), ("paint", s.zone == "paint")):
        g = s[mask].groupby("player_id").made
        out[name] = (g.sum().astype(float), g.size().astype(float))
    return out


def blend_old_finishing(c: dict) -> pd.Series:
    rim, paint = rates(c["rim"]), rates(c["paint"])
    return (0.7 * rim).add(0.3 * paint, fill_value=np.nan).dropna()


def selection(t, full: dict, split: dict) -> tuple[pd.DataFrame, dict]:
    rows = []
    chosen: dict[str, tuple] = {}
    for metric in STAGE_METRICS:
        spec = SPECS[metric]
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
        test = second25[1][second25[1] > 0].index
        full24 = full["E2024"][metric]
        past24 = (*full24, league_level(*full24))
        offset = None
        if metric == "corner3_pct":
            sp, role_, w = chosen["three_pct"]
            three_first = split["E2025"][0]["three_pct"]
            lvl = league_level(*three_first)
            ft1 = ft_skill(*split["E2025"][0]["ft_pct"], [(*full["E2024"]["ft_pct"], league_level(*full["E2024"]["ft_pct"]), 1.0)])
            ft24 = ft_skill(*full["E2024"]["ft_pct"])
            beta3 = fit_role([(*full["E2024"]["three_pct"], league_level(*full["E2024"]["three_pct"]), t.window("E2024").people, ft24)])
            off3 = role_offset(test, three_first[1], t.window("E2025").people, beta3, ft1)
            th, _, _ = shrink(*three_first, sp, lvl, off3 if role_ else None,
                              [(*full["E2024"]["three_pct"], league_level(*full["E2024"]["three_pct"]), w)] if w else None, test)
            offset = th - lvl
        elif metric != "three_rate" and metric != "mid_rate":
            use_ft = spec.ft_prior
            ft1 = ft_skill(*split["E2025"][0]["ft_pct"], [(*full["E2024"]["ft_pct"], league_level(*full["E2024"]["ft_pct"]), 1.0)]) if use_ft else None
            ft24 = ft_skill(*full["E2024"]["ft_pct"]) if use_ft else None
            sample = (*full24, league_level(*full24), t.window("E2024").people, *([ft24] if use_ft else []))
            offset = role_offset(test, first25[1], t.window("E2025").people, fit_role([sample]), ft1)
        else:
            beta = fit_role([(*full24, league_level(*full24), t.window("E2024").people)])
            offset = role_offset(test, first25[1], t.window("E2025").people, beta)

        def run(k: float, role: bool, w: float) -> float:
            return gain(make(k), first25, second25, offset if role else None, [(*past24, w)] if w > 0 else None)

        plain = max(run(k, False, 0) for k in K_GRID)
        with_role = max(run(k, True, 0) for k in K_GRID)
        with_carry = max(run(k, False, w) for k in K_GRID for w in CARRY_GRID)
        use_role = with_role - plain >= MIN_IMPROVEMENT
        grid = {w: max(run(k, use_role, w) for k in K_GRID) for w in CARRY_GRID}
        best_w = max(grid, key=grid.get)
        use_w = best_w if grid[best_w] - grid[0.0] >= MIN_IMPROVEMENT else 0.0
        results = {k: run(k, use_role, use_w) for k in K_GRID}
        final_k = max(results, key=results.get)
        chosen[metric] = (make(final_k), use_role, use_w)
        cover = coverage(make(final_k), first25, second25, offset if use_role else None, [(*past24, use_w)] if use_w > 0 else None)
        rows.append({"metrik": metric, "k_moment": round(k_moment) if np.isfinite(k_moment) else "sonsuz", "k_test": k_test,
                     "iki_sezon_kazanç": both[k_test], "E25_yalın": plain, "E25_beklenti": with_role, "E25_geçmiş": with_carry,
                     "seçilen_k": final_k, "seçilen_beklenti": use_role, "seçilen_w": use_w, "seçilen_kazanç": results[final_k],
                     "aralık_kapsama": cover, "koddaki": f"k={spec.k:g} rol={spec.role} w={spec.carry:g}"})
    return pd.DataFrame(rows), chosen


def low_volume_test(t, full: dict, split: dict) -> pd.DataFrame:
    """Do low-volume shooters miss more later than the model expects? Bands from the first half only."""
    rows = []
    first, second = split["E2025"][0], split["E2025"][1]
    s1, n1 = first["three_pct"]
    s2, n2 = second["three_pct"]
    poss = first["three_rate"][1]
    test = n2[n2 > 0].index
    volume = 100 * n1.reindex(test).fillna(0) / poss.reindex(test).clip(lower=1).fillna(1)
    full24 = full["E2024"]["three_pct"]
    past = [(*full24, league_level(*full24), 1.0)]
    level = league_level(s1, n1)
    ft1 = ft_skill(*first["ft_pct"], [(*full["E2024"]["ft_pct"], league_level(*full["E2024"]["ft_pct"]), 1.0)])
    ft24 = ft_skill(*full["E2024"]["ft_pct"])
    beta = fit_role([(*full24, league_level(*full24), t.window("E2024").people, ft24)])
    offset = role_offset(test, n1, t.window("E2025").people, beta, ft1)
    league_only, _, _ = shrink(s1, n1, Spec("prop", 400), level, None, None, test)
    model, _, _ = shrink(s1, n1, SPECS["three_pct"], level, offset, past, test)
    bands = pd.cut(volume, VOLUME_BANDS, right=False)
    for band, idx in volume.groupby(bands, observed=True).groups.items():
        w = n2.reindex(idx)
        rows.append({"3PA_100": str(band), "oyuncu": len(idx), "gelecek_3PA": int(w.sum()),
                     "gerçek": float(s2.reindex(idx).fillna(0).sum() / w.sum()),
                     "eski_tahmin": float((league_only.reindex(idx) * w).sum() / w.sum()),
                     "yeni_tahmin": float((model.reindex(idx) * w).sum() / w.sum())})
    return pd.DataFrame(rows)


def corner_check(t) -> tuple[pd.DataFrame, pd.DataFrame]:
    games = pd.read_parquet(TABLES_DIR / "games.parquet")[["season", "gamecode", "home"]]
    s = t.shots[(t.shots.value == 3) & ~t.shots.is_heave & t.shots.zone_group.isin(["corner3", "above_break3"])]
    per = s.groupby(["season", "player_id", "zone_group"]).made.agg(["sum", "size"]).unstack("zone_group")
    per.columns = [f"{a}_{b}" for a, b in per.columns]
    both = per[(per.size_corner3 >= MIN_SAME_PLAYER) & (per.size_above_break3 >= MIN_SAME_PLAYER)]
    corner = both.sum_corner3.sum() / both.size_corner3.sum()
    above = both.sum_above_break3.sum() / both.size_above_break3.sum()
    w = both.size_corner3
    weighted = ((both.sum_corner3 / both.size_corner3 - both.sum_above_break3 / both.size_above_break3) * w).sum() / w.sum()
    same = pd.DataFrame([
        {"ölçüm": "Lig: köşe", "değer": s[s.zone_group == "corner3"].made.mean()},
        {"ölçüm": "Lig: üst kavis", "değer": s[s.zone_group == "above_break3"].made.mean()},
        {"ölçüm": f"Aynı oyuncular ({len(both)}, ikisinde en az {MIN_SAME_PLAYER}): köşe", "değer": corner},
        {"ölçüm": "Aynı oyuncular: üst kavis", "değer": above},
        {"ölçüm": "Aynı oyuncu farkı, köşe denemesi ağırlıklı", "değer": weighted},
    ])
    vis = s.merge(games, on=["season", "gamecode"])
    vis = vis[vis.team != vis.home]
    rows = []
    for name, group in (("köşe", "corner3"), ("üst kavis", "above_break3")):
        d = vis[vis.zone_group == group].groupby(["season", "home"]).made.agg(["size", "mean"])
        d = d[d["size"] >= MIN_ARENA_ATTEMPTS]
        p = (d["mean"] * d["size"]).sum() / d["size"].sum()
        disp = ((d["mean"] - p) ** 2 * d["size"] / (p * (1 - p))).sum() / (len(d) - 1)
        rows.append({"bölge": name, "salon": len(d), "en_düşük": d["mean"].min(), "en_yüksek": d["mean"].max(), "yayılım_oranı": disp})
    return same, pd.DataFrame(rows)


def season_ahead(t, full: dict) -> pd.DataFrame:
    """E2024 alone predicting all of E2025: within a season, team and arena stay the same and can
    look like skill; across seasons many players change both."""
    rows = []
    for metric in ("three_pct", "mid_pct", "inside_adj"):
        spec = SPECS[metric]
        first, second = full["E2024"][metric], full["E2025"][metric]
        # shrink() takes this season's level from the first window, here E2024
        gains = {k: gain(Spec(spec.kind, k), first, second) for k in K_GRID}
        best = max(gains, key=gains.get)
        movers = t.window("E2024").player_games.groupby("player_id").team.last()
        stayers = t.window("E2025").player_games.groupby("player_id").team.last()
        common = movers.index.intersection(stayers.index)
        same_team = common[movers.reindex(common) == stayers.reindex(common)]
        changed = common[movers.reindex(common) != stayers.reindex(common)]
        r = {}
        for name, group in (("aynı_takım", same_team), ("takım_değiştiren", changed)):
            n1, n2 = first[1].reindex(group).fillna(0), second[1].reindex(group).fillna(0)
            keep = group[(n1 >= SEASON_AHEAD_MIN) & (n2 >= SEASON_AHEAD_MIN)]
            r[f"r_{name}"] = float(rates(first).reindex(keep).corr(rates(second).reindex(keep)))
            r[f"n_{name}"] = len(keep)
        rows.append({"metrik": metric, "en_iyi_k": best, "kazanç": gains[best], "kazanç_k_seçilen": gains.get(spec.k, np.nan), **r})
    return pd.DataFrame(rows)


def main() -> None:
    t = load_tables()
    full = {x: counts(t.window(x)) for x in REF}
    split, old_full, old_split, minutes = {}, {}, {}, {}
    for x in REF:
        w = t.window(x)
        first = first_half_games(w.player_games)
        rest = set(w.player_games.gamecode) - first
        split[x] = (counts(t.window(x, first)), counts(t.window(x, rest)))
        old_full[x] = old_rates(w)
        old_split[x] = (old_rates(t.window(x, first)), old_rates(t.window(x, rest)))
        minutes[x] = w.player_games.groupby("player_id").minutes.sum()
        minutes[(x, "halves")] = tuple(w.player_games[w.player_games.gamecode.isin(g)].groupby("player_id").minutes.sum()
                                       for g in (first, rest))

    chosen_table, _ = selection(t, full, split)
    chosen_table.to_csv(AUDIT_DIR / "stage4_selection.csv", index=False)
    volume = low_volume_test(t, full, split)
    same, arenas = corner_check(t)
    ahead = season_ahead(t, full)

    both_seasons = minutes["E2024"][minutes["E2024"] >= SEASON_MINUTES].index.intersection(
        minutes["E2025"][minutes["E2025"] >= SEASON_MINUTES].index)

    def half_players(x):
        a, b = minutes[(x, "halves")]
        return a[a >= HALF_MINUTES].index.intersection(b[b >= HALF_MINUTES].index)

    measure_rows = []
    for key, new_metric in (("three_point", "three_pct"), ("three_point", "three_rate"), ("mid_range", "mid_pct"),
                            ("mid_range", "mid_rate"), ("finishing", "inside_adj")):
        def old_value(store):
            return blend_old_finishing(store) if key == "finishing" else rates(store[OLD_STAGE[key]])

        measure_rows.append({
            "özellik": key, "yeni_metrik": new_metric,
            "yarı_r_eski": float(np.mean([split_r(old_value(old_split[x][0]), old_value(old_split[x][1]), half_players(x)) for x in REF])),
            "yarı_r_yeni": float(np.mean([split_r(rates(split[x][0][new_metric]), rates(split[x][1][new_metric]), half_players(x)) for x in REF])),
            "sezon_r_eski": split_r(old_value(old_full["E2024"]), old_value(old_full["E2025"]), both_seasons),
            "sezon_r_yeni": split_r(rates(full["E2024"][new_metric]), rates(full["E2025"][new_metric]), both_seasons)})
    measures = pd.DataFrame(measure_rows)

    metrics = season_metrics(t)
    new = score_frames(metrics, tuple(a for a in ATTRIBUTES_V2 if a.key in KEYS))
    ratings = pd.read_parquet(TABLES_DIR / "ratings_season_v1.parquet")
    extra = metrics[["season", "player_id", "three_non_shooter", "mid_non_shooter", "corner3_pct", "n_corner3_pct"]]
    j = (ratings[["season", "player_id", "player", "team", "games", "minutes", "qualified"] + list(KEYS)]
         .merge(new, on=["season", "player_id"], suffixes=("_old", "")).merge(extra, on=["season", "player_id"]))
    box = t.player_games.groupby(["season", "player_id"]).agg(fg3m=("fg3m", "sum"), fg3a=("fg3a", "sum"), g=("gamecode", "size")).reset_index()
    j = j.merge(box, on=["season", "player_id"])
    j["tpa_g"] = j.fg3a / j.g
    j["raw3"] = j.fg3m / j.fg3a.replace(0, np.nan)
    pd.concat([j[["season", "player_id", "player", "team", "games", "minutes", "qualified"]].assign(
        attribute=k, old=j[f"{k}_old"], new=j[k], lo=j[f"{k}_lo"], hi=j[f"{k}_hi"], low_data=j[f"{k}_low_data"]) for k in KEYS]
    ).to_csv(AUDIT_DIR / "stage4_ratings.csv", index=False)

    q = j[j.qualified]
    band = q.assign(bant=pd.cut(q.tpa_g, GAME_BANDS)).groupby("bant", observed=True).agg(
        oyuncu=("three_point", "size"), eski_ort=("three_point_old", "mean"), yeni_ort=("three_point", "mean"),
        eski_max=("three_point_old", "max"), yeni_max=("three_point", "max"), ham_isabet=("raw3", "mean")).reset_index()
    band["bant"] = band.bant.astype(str)

    full_seasons = j[j.season.isin(REF) & (j.minutes >= SEASON_MINUTES)]
    q25, q26 = j[(j.season == "E2025") & j.qualified], j[(j.season == "E2026") & j.qualified]
    summary = pd.DataFrame([{
        "özellik": k, "eski_yeni_r": full_seasons[f"{k}_old"].corr(full_seasons[k]),
        "3+_değişen_%": 100 * ((full_seasons[f"{k}_old"] - full_seasons[k]).abs() >= 3).mean(),
        "takım_payı_eski": team_share(full_seasons, f"{k}_old"), "takım_payı_yeni": team_share(full_seasons, k),
        "aralık_E25": (q25[f"{k}_hi"] - q25[f"{k}_lo"]).mean(), "aralık_E26": (q26[f"{k}_hi"] - q26[f"{k}_lo"]).mean(),
        "az_veri_E25": q25[f"{k}_low_data"].mean(), "az_veri_E26": q26[f"{k}_low_data"].mean(),
        "18+_E26_eski": int((q26[f"{k}_old"] >= 18).sum()), "18+_E26_yeni": int((q26[k] >= 18).sum())} for k in KEYS])

    out = ["# Aşama 4: Şut özellikleri\n", "Üretim puanları değişmedi.\n", "## 1. Parametre seçimi\n",
           f"Beklenti: üçlük ve orta mesafe için boy, pozisyon, serbest atış; hacim ve bitiricilik için boy, pozisyon; köşe için "
           f"oyuncunun üçlük tahmini. Eşik {MIN_IMPROVEMENT} puan.\n", table(chosen_table), "",
           "## 2. Az atanlar tahminin altında mı kalıyor? (E2025 ikinci yarı)\n",
           "`eski_tahmin`: lig ortalamasına k=400. `yeni_tahmin`: seçili model.\n", table(volume), "",
           "## 3. Köşe üçlük gerçek mi?\n", table(same), "", table(arenas), "",
           "## 4. Eski ve yeni tanım\n", table(measures), "",
           "**Sezon sonrası tahmin:** E2024'ten yalnızca E2025. Korelasyonlar her iki sezon en az "
           f"{SEASON_AHEAD_MIN} deneme yapan oyuncular içindir.\n", table(ahead), "",
           "## 5. Puan karşılaştırması\n", table(summary), "",
           "## 6. Maç başı üçlük denemesine göre Üçlük puanı (tüm sezonlar, qualified)\n", table(band), "",
           f"\"Üçlük kullanmıyor\" etiketi: E2025 {int(q25.three_non_shooter.sum())}, E2026 {int(q26.three_non_shooter.sum())} oyuncu. "
           f"Ortalama Üçlük puanı: {q[q.three_non_shooter].three_point.mean():.1f}, en yüksek {int(q[q.three_non_shooter].three_point.max())}.\n",
           "## 7. E2025 en yüksek ve en düşük (en az 500 dakika)\n"]
    e25 = j[(j.season == "E2025") & (j.minutes >= SEASON_MINUTES)]
    for k in KEYS:
        order = e25.sort_values([k, f"{k}_old"], ascending=False)
        fmt = lambda d: ", ".join(f"{r.player.title()} {getattr(r, k)} ({getattr(r, k + '_old')})" for r in d.itertuples())  # noqa: E731
        out += [f"**{k}**", f"- Üst: {fmt(order.head(8))}", f"- Alt: {fmt(order.tail(5))}", ""]
    out += ["Parantez içi eski puan.\n", "## 8. En çok değişenler (E2025, en az 500 dakika)\n"]
    moves = []
    for k in KEYS:
        d = e25.assign(fark=e25[k] - e25[f"{k}_old"], attr=k, eski=e25[f"{k}_old"], yeni=e25[k])
        moves.append(d.reindex(d.fark.abs().sort_values(ascending=False).index).head(6)[["attr", "player", "team", "eski", "yeni", "fark"]])
    out += [table(pd.concat(moves)), "", "## 9. İzlenen oyuncular (E2026)\n"]
    watch = j[(j.season == "E2026") & j.player.str.contains("|".join(WATCH), case=False)].assign(ham_3=lambda d: d.fg3m.astype(str) + "/" + d.fg3a.astype(str))
    out += [table(watch[["player", "ham_3", "three_point_old", "three_point", "three_point_lo", "three_point_hi", "three_point_low_data",
                         "finishing_old", "finishing", "mid_range_old", "mid_range"]]), "", "Tüm oyuncular: `stage4_ratings.csv`.\n"]
    text = "\n".join(out)
    (AUDIT_DIR / "stage4.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
