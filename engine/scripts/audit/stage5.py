"""Stage 5 audit: lineup models for the three defensive attributes.

    uv run python scripts/audit/stage5.py

Read-only: writes only under data/audit/. Pota Koruma is reported with and without a role prior:
the owner's reference list holds only big men, so with a height-based prior, height alone could
pass the test. E2026 takes no part in choosing parameters.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from foundation import table  # noqa: E402
from stage3 import REF, first_half_games, team_share  # noqa: E402

from bk.config import AUDIT_DIR, TABLES_DIR  # noqa: E402
from bk.ratings.attributes import Attribute  # noqa: E402
from bk.ratings.defense import (DEFENSE_ATTRIBUTES, DEFENSE_K, EFFECTS, FEATURES, PREV_WEIGHT, RIM_BLOCK_WEIGHT,  # noqa: E402
                                Design, EffectConfig, attach_effect, build_effect, fit_role_effect, holdout_gain,
                                on_off_card, possession_table, role_features, role_prior)
from bk.ratings.method import fixed_reference, score_fixed  # noqa: E402
from bk.ratings.metrics_v2 import SPECS, counts, load_tables, season_metrics  # noqa: E402

LAMBDAS = (100, 200, 400, 800, 1500, 3000, 6000, 12000, 24000, 48000)
TARGETS = ("inside_points", "three_attempts", "points")
SEASON_MINUTES = 500
REFERENCE_MINUTES = 250
RIM_GATE_TEAM, RIM_GATE_STABILITY = 0.10, 0.5
TIER_GATE_STABILITY = 0.3
WATCH = ["CROWDER", "FRANCISCO", "THOMPSON, DARIUS", "BADIO", "MONTERO", "COSTELLO", "TAVARES", "DIBARTOLOMEO", "WASHINGTON, DUANE", "MILLS, PATTY"]
RIM_VARIANTS = (  # label, lam, prior, use_team, block weight
    ("Yalnız saha içi, beklenti yok", 1500, "yok", False, 0.0),
    ("Yalnız saha içi, rol", 1500, "rol", False, 0.0),
    ("Saha içi + takım ayrımı", 1500, "yok", True, 0.0),
    ("Saha içi + takım + blok %30", 1500, "yok", True, 0.3),
    ("Saha içi + takım + blok %50, beklenti yok", 1500, "yok", True, 0.5),
    ("Saha içi + takım + blok %50, rol", 1500, "rol", True, 0.5),
    ("SEÇİLEN: saha içi + takım + blok %50, rol + geçmiş", 1500, "ikisi", True, 0.5),
    ("Saha içi + takım + blok %60, rol + geçmiş", 1500, "ikisi", True, 0.6),
)


def cut(poss: pd.DataFrame, games: set) -> pd.DataFrame:
    return poss[poss.gamecode.isin(games)]


def lambda_table(poss: dict, games: dict) -> pd.DataFrame:
    rows = []
    for target in TARGETS:
        for use_off in (False, True):
            designs = {x: Design.build(cut(poss[x], games[x][0]), target, use_off) for x in REF}
            halves = {lam: float(np.mean([holdout_gain(None, cut(poss[x], games[x][1]), target, lam, None, use_off, designs[x]) for x in REF]))
                      for lam in LAMBDAS}
            year = Design.build(poss["E2024"], target, use_off)
            ahead = {lam: holdout_gain(None, poss["E2025"], target, lam, None, use_off, year) for lam in LAMBDAS}
            best_h, best_a = max(halves, key=halves.get), max(ahead, key=ahead.get)
            rows.append({"hedef": target, "rakip_hücum_kontrolü": use_off, "yarı_en_iyi_λ": best_h, "yarı_kazanç": halves[best_h],
                         "sezon_en_iyi_λ": best_a, "sezon_kazanç": ahead[best_a]})
    return pd.DataFrame(rows)


def prior_table(t, poss: dict, games: dict) -> pd.DataFrame:
    rows = []
    c24 = counts(t.window("E2024"))
    c1 = counts(t.window("E2025", games["E2025"][0]))
    for name, cfg in EFFECTS.items():
        d24 = Design.build(poss["E2024"], cfg.target)
        b24 = d24.solve(cfg.lam)
        coefficients = fit_role_effect([b24.beta], [role_features(t.window("E2024"), c24, b24.index)], [b24.n])
        first, second = cut(poss["E2025"], games["E2025"][0]), cut(poss["E2025"], games["E2025"][1])
        design = Design.build(first, cfg.target)
        plain = design.solve(cfg.lam)
        role = role_prior(role_features(t.window("E2025"), c1, plain.index), coefficients, plain.n)
        prev = PREV_WEIGHT * b24.beta
        variants = {"yok": None, "rol": role, "geçmiş": prev, "ikisi": 0.5 * prev.reindex(role.index).fillna(0) + 0.5 * role}
        row = {"metrik": name, "λ": cfg.lam}
        for label, prior in variants.items():
            row[label] = holdout_gain(None, second, cfg.target, cfg.lam, prior, False, design)
        row["rol_katsayıları"] = ", ".join(f"{n}={c:.4f}" for n, c in zip(FEATURES, coefficients[1:]))
        rows.append(row)
    return pd.DataFrame(rows)


def rate(metrics: pd.DataFrame, attribute: Attribute, prior_k: dict) -> pd.DataFrame:
    reference = fixed_reference(metrics)
    frames = [score_fixed(g.set_index("player_id"), reference, (attribute,), prior_k).assign(season=season).reset_index()
              for season, g in metrics.groupby("season")]
    return pd.concat(frames, ignore_index=True)


def gate_row(label: str, d: pd.DataFrame, key: str, both, best_names, rule) -> dict:
    f = d[d.season.isin(REF) & (d.minutes >= SEASON_MINUTES)]
    pv = f.pivot(index="player_id", columns="season", values=key).reindex(both)
    best = d[d.player.isin(best_names) & (d.minutes >= REFERENCE_MINUTES) & d.season.isin(REF)]
    guards = d[(d.position == rule["position"]) & (d.height <= rule["max_height_cm"]) & (d.minutes >= rule["min_minutes"]) & d.season.isin(REF)]
    top = pd.concat([g.sort_values(key, ascending=False).head(20) for _, g in f.groupby("season")])
    return {"model": label, "takım_payı": team_share(f, key), "sezon_r": pv.E2024.corr(pv.E2025), "boy_r": f[key].corr(f.height),
            "liste_ort": best[key].mean(), "liste_16+": f"{int((best[key] >= 16).sum())}/{len(best)}", "guard_ort": guards[key].mean(),
            "guard_16+": int((guards[key] >= 16).sum()), "ilk20_G": int((top.position == "Guard").sum()), "ilk20_C": int((top.position == "Center").sum())}


def main() -> None:
    t = load_tables()
    seasons = sorted(t.player_games.season.unique())
    poss = {x: possession_table(t.window(x)) for x in seasons}
    games = {}
    for x in REF:
        first = first_half_games(t.window(x).player_games)
        games[x] = (first, set(t.window(x).player_games.gamecode) - first)

    lam_table = lambda_table(poss, games)
    lam_table.to_csv(AUDIT_DIR / "stage5_lambda.csv", index=False)
    priors = prior_table(t, poss, games)

    base = season_metrics(t)
    ratings = pd.read_parquet(TABLES_DIR / "ratings_season_v1.parquet")
    people = t.people[["season", "player_id", "height", "position"]]
    meta = base[["season", "player_id", "player", "team", "minutes"]].merge(people, on=["season", "player_id"], how="left")
    meta = meta.merge(ratings[["season", "player_id", "qualified", "rim_protection", "perimeter_defense", "team_defense"]].rename(
        columns={"rim_protection": "rp_old", "perimeter_defense": "pd_old", "team_defense": "td_old"}), on=["season", "player_id"])
    counts_both = meta[meta.season.isin(REF) & (meta.minutes >= SEASON_MINUTES)].groupby("player_id").season.nunique()
    both = counts_both[counts_both == 2].index
    lists = json.loads((Path(__file__).parent / "reference_lists.json").read_text(encoding="utf-8"))["rim_protection"]
    best_names = [p["name"] for p in lists["best_players"]]
    rule = lists["worst_rule"]

    rows = [gate_row("ESKİ FORMÜL", meta, "rp_old", both, best_names, rule)]
    chosen_rim = None
    for label, lam, prior, use_team, weight in RIM_VARIANTS:
        effect = build_effect(t, poss, EffectConfig("inside_points", lam, prior, use_team), seasons)
        m = attach_effect(base[["season", "player_id", "minutes", "blk_share", "n_blk_share", "se_blk_share"]], effect, "rim_effect")
        components = (("rim_effect", 1, 1),) if weight == 0 else (("rim_effect", 1 - weight, 1), ("blk_share", weight, 1))
        attribute = Attribute("rim_protection", "Pota Koruma", "savunma", "tahmini", components)
        d = meta.merge(rate(m, attribute, {"rim_effect": lam, "blk_share": SPECS["blk_share"].k}), on=["season", "player_id"])
        rows.append(gate_row(label, d, "rim_protection", both, best_names, rule))
        if label.startswith("SEÇİLEN"):
            chosen_rim = d.merge(m[["season", "player_id", "rim_effect", "se_rim_effect", "n_rim_effect"]], on=["season", "player_id"])
    variants = pd.DataFrame(rows)
    card = on_off_card(t, pd.concat(poss.values(), ignore_index=True))
    out_rim = chosen_rim.merge(card, on=["season", "player_id"], how="left")
    out_rim.to_csv(AUDIT_DIR / "stage5_rim.csv", index=False)

    perim_attr = next(a for a in DEFENSE_ATTRIBUTES if a.key == "perimeter_defense")
    team_attr = next(a for a in DEFENSE_ATTRIBUTES if a.key == "team_defense")
    perim_cols = ["season", "player_id", "minutes", "stl_rate", "n_stl_rate", "se_stl_rate", "opp_three_pct", "n_opp_three_pct", "se_opp_three_pct"]

    def perimeter(cfg: EffectConfig) -> pd.DataFrame:
        m = attach_effect(base[perim_cols], build_effect(t, poss, cfg, seasons), "three_att_effect")
        k = {"three_att_effect": cfg.lam, "stl_rate": SPECS["stl_rate"].k, "opp_three_pct": SPECS["opp_three_pct"].k}
        return meta.merge(rate(m, perim_attr, k), on=["season", "player_id"])

    def team_def(cfg: EffectConfig) -> pd.DataFrame:
        m = attach_effect(base[["season", "player_id", "minutes"]], build_effect(t, poss, cfg, seasons), "team_effect")
        return meta.merge(rate(m, team_attr, {"team_effect": cfg.lam}), on=["season", "player_id"])

    three_cfg, points_cfg = EFFECTS["three_att_effect"], EFFECTS["team_effect"]
    frames = {"Çevre Savunması (seçilen)": (perimeter(three_cfg), "perimeter_defense", "pd_old"),
              "Çevre, geçmişsiz": (perimeter(EffectConfig("three_attempts", three_cfg.lam, "yok", three_cfg.use_team)), "perimeter_defense", "pd_old"),
              "Savunma Etkisi (seçilen)": (team_def(points_cfg), "team_defense", "td_old"),
              "Savunma Etkisi, geçmişsiz": (team_def(EffectConfig("points", points_cfg.lam, "yok")), "team_defense", "td_old")}
    others = []
    for name, (d, key, old) in frames.items():
        f = d[d.season.isin(REF) & (d.minutes >= SEASON_MINUTES)]
        pv = f.pivot(index="player_id", columns="season", values=key).reindex(both)
        pv_old = f.pivot(index="player_id", columns="season", values=old).reindex(both)
        e26 = d[(d.season == "E2026") & d.qualified]
        others.append({"özellik": name, "sezon_r_eski": pv_old.E2024.corr(pv_old.E2025), "sezon_r_yeni": pv.E2024.corr(pv.E2025),
                       "takım_payı_eski": team_share(f, old), "takım_payı_yeni": team_share(f, key), "eski_yeni_r": f[old].corr(f[key]),
                       "aralık_E25": (f[f.season == "E2025"][f"{key}_hi"] - f[f.season == "E2025"][f"{key}_lo"]).mean(),
                       "az_veri_E26": e26[f"{key}_low_data"].mean()})
    other = pd.DataFrame(others)
    pd.concat([frames["Çevre Savunması (seçilen)"][0][["season", "player_id", "player", "perimeter_defense", "perimeter_defense_lo", "perimeter_defense_hi", "pd_old"]].set_index(["season", "player_id", "player"]),
               frames["Savunma Etkisi (seçilen)"][0][["season", "player_id", "player", "team_defense", "team_defense_lo", "team_defense_hi", "td_old"]].set_index(["season", "player_id", "player"])], axis=1).to_csv(AUDIT_DIR / "stage5_other.csv")

    def listing(d, key, n=10):
        e = d[(d.season == "E2025") & (d.minutes >= SEASON_MINUTES)].sort_values(key, ascending=False)
        return ", ".join(f"{r.player.title()} {getattr(r, key)}" for r in e.head(n).itertuples())

    out = ["# Aşama 5: Savunma modelleri\n", "Üretim puanları değişmedi. Kazanç: başka pencerenin dizilişlerini tahminde sabite göre hata azalması (%). "
           "Tek hücum çok gürültülü olduğu için değerler küçüktür, önemli olan karşılaştırmadır.\n",
           "## 1. λ seçimi\n", table(lam_table), "", "## 2. Beklenti türü (E2025 ikinci yarı kazancı, %)\n", table(priors), "",
           "## 3. Pota Koruma: modeller\n",
           f"Geçiş: takım payı en fazla {RIM_GATE_TEAM}, sezon_r en az {RIM_GATE_STABILITY}. `liste`: referans listen ({REFERENCE_MINUTES}+ dk, E2024-E2025). "
           "`guard`: Guard, en fazla 188 cm, 500+ dk. `ilk20`: iki sezonun ilk 20'lerindeki toplam guard ve pivot. Geçmişli modellerde sezon_r mekanik olarak yükselir.\n",
           table(variants), "", f"Bileşenler: saha içi etki %{100 * (1 - RIM_BLOCK_WEIGHT):.0f}, blok payı %{100 * RIM_BLOCK_WEIGHT:.0f}.\n",
           "## 4. E2025 Pota Koruma (500+ dk)\n"]
    e = out_rim[(out_rim.season == "E2025") & (out_rim.minutes >= SEASON_MINUTES)].sort_values(["rim_protection", "rp_old"], ascending=False)
    fmt = lambda d: ", ".join(f"{r.player.title()} ({r.position[0]}, {int(r.height)}) {r.rim_protection} ({r.rp_old})" for r in d.itertuples())  # noqa: E731
    out += ["**İlk 20:** " + fmt(e.head(20)), "", "**Son 8:** " + fmt(e.tail(8)), "", "Parantez içi son sayı eski puan.\n",
            "## 5. Referans listen\n", table(out_rim[out_rim.player.isin(best_names)].sort_values(["player", "season"])[["season", "player", "team", "height", "minutes", "rp_old", "rim_protection", "rim_protection_lo", "rim_protection_hi", "rim_protection_low_data"]]), "",
            "## 6. Kısa guardlarda en yüksekler\n"]
    g = out_rim[(out_rim.position == rule["position"]) & (out_rim.height <= rule["max_height_cm"]) & (out_rim.minutes >= rule["min_minutes"])].sort_values("rim_protection", ascending=False)
    w = out_rim[out_rim.player.str.contains("|".join(WATCH), case=False) & (out_rim.minutes >= 100)].sort_values(["player", "season"])
    out += [table(g[["season", "player", "height", "minutes", "rp_old", "rim_protection", "rim_protection_lo", "rim_protection_hi"]].head(8)), "",
            "## 7. İzlenen oyuncular\n",
            table(w[["season", "player", "position", "height", "minutes", "rp_old", "rim_protection", "rim_protection_lo", "rim_protection_hi", "rim_effect", "opp_inside_fga_on", "opp_inside_fga_off", "opp_inside_pct_on", "opp_inside_pct_off"]]), "",
            "`opp_inside_*`: rakibin pota + boyalı alan denemesi / 100 hücum ve isabeti, oyuncu sahada ve kenarda, oynadığı maçlarda.\n",
            "## 8. Çevre Savunması ve Savunma Etkisi\n", f"Geçiş: sezon_r en az {TIER_GATE_STABILITY}, yoksa Düşük/Orta/Yüksek kademesi. Geçmişsiz satır, kararın dayanağıdır.\n", table(other), "",
            "**E2025 Çevre Savunması ilk 10:** " + listing(frames["Çevre Savunması (seçilen)"][0], "perimeter_defense"), "",
            "**E2025 Savunma Etkisi ilk 10:** " + listing(frames["Savunma Etkisi (seçilen)"][0], "team_defense"), ""]
    text = "\n".join(out)
    (AUDIT_DIR / "stage5.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
