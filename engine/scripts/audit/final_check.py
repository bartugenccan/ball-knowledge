"""Final check on E2026, the one season never used to choose a parameter.

    uv run python scripts/audit/final_check.py

Everything is frozen before this runs. The first half of E2026's games yields a rating under the
old and the new method; the second half is what they must anticipate. Results are reported as
they come: nothing is tuned on them.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from foundation import table  # noqa: E402
from stage3 import first_half_games, team_share  # noqa: E402

from bk.config import AUDIT_DIR, TABLES_DIR  # noqa: E402
from bk.ratings.attributes import qualified, score  # noqa: E402
from bk.ratings.legacy_build import CARRY_WEIGHTS  # noqa: E402
from bk.ratings.catalog import PRIOR_K, RATING_ATTRIBUTES  # noqa: E402
from bk.ratings.defense import EFFECTS, Design, add_defense_metrics, possession_table  # noqa: E402
from bk.ratings.mental import add_mental_metrics, load_counts  # noqa: E402
from bk.ratings.method import fixed_reference, score_fixed  # noqa: E402
from bk.ratings.metrics import PRIOR_K as OLD_K  # noqa: E402
from bk.ratings.metrics import WindowData, carry_counts, compute_metrics, league_priors, shooter_expectation  # noqa: E402
from bk.ratings.metrics_v2 import INFO_METRICS, SPECS, Spec, Tables, counts, fit_role, ft_skill, league_level, load_tables, role_offset, season_metrics, shrink  # noqa: E402

SEASON = "E2026"
MIN_MINUTES = 60
OLD_METRIC_K = {"ft_pct": "ft_pct", "stl_rate": "stl_rate", "blk_share": "blk_rate", "foul_rate": "pf_rate", "orb_share": "orb_rate",
                "drb_share": "drb_rate", "tov_share": "tov_pct", "fd_rate": "ftr", "trip_rate": "ftr", "creation_rate": "unast_rate",
                "ast_share": "ast_rate", "created_rate": "ast_rate", "three_pct": "three_pct", "mid_pct": "mid_pct", "inside_adj": "paint_pct"}
TARGET = {"free_throw": ("ft_pct", 1), "steals": ("stl_rate", 1), "shot_blocking": ("blk_share", 1), "discipline": ("foul_rate", -1),
          "off_rebounding": ("orb_share", 1), "def_rebounding": ("drb_share", 1), "ball_security": ("tov_share", -1),
          "drawing_fouls": ("fd_rate", 1), "shot_creation": ("creation_rate", 1), "passing": ("ast_share", 1),
          "three_point": ("three_pct", 1), "mid_range": ("mid_pct", 1), "finishing": ("inside_adj", 1)}


def spearman(a: pd.Series, b: pd.Series) -> float:
    return float(a.rank().corr(b.rank()))


def only_games(t: Tables, season: str, games: set) -> Tables:
    def cut(df):
        return df if df is None else df[(df.season != season) | df.gamecode.isin(games)]

    return replace(t, shots=cut(t.shots), player_games=cut(t.player_games), possessions=cut(t.possessions), rebounds=cut(t.rebounds),
                   fouls=cut(t.fouls), trips=cut(t.trips), events=cut(t.events), stints=cut(t.stints))


def metric_gains(t: Tables, first: set, second: set) -> pd.DataFrame:
    """Prediction of the second half for every count metric, frozen setup against league-only old k."""
    c1, c2 = counts(t.window(SEASON, first)), counts(t.window(SEASON, second))
    history = {x: counts(t.window(x)) for x in ("E2024", "E2025")}
    levels = {x: {m: league_level(*history[x][m]) for m in SPECS} for x in history}
    ft_hist = {"E2024": ft_skill(*history["E2024"]["ft_pct"]),
               "E2025": ft_skill(*history["E2025"]["ft_pct"], [(*history["E2024"]["ft_pct"], levels["E2024"]["ft_pct"], 1.0)])}
    ft_now = ft_skill(*c1["ft_pct"], [(*history["E2025"]["ft_pct"], levels["E2025"]["ft_pct"], 1.0),
                                      (*history["E2024"]["ft_pct"], levels["E2024"]["ft_pct"], 0.5)])
    rows = []
    for metric, spec in SPECS.items():
        if metric in INFO_METRICS or metric == "opp_three_pct":
            continue
        s2, n2 = c2[metric]
        test = n2[n2 > 0].index
        s1, n1 = c1[metric]
        level = league_level(s1, n1)
        x2 = s2.reindex(test).fillna(0) / n2.reindex(test)
        w = n2.reindex(test)

        def error(pred):
            return float((w * (x2 - pred) ** 2).sum() / w.sum())

        league = error(pd.Series(level, index=test))
        offset = None
        if spec.role:
            beta = fit_role([(*history[x][metric], levels[x][metric], t.window(x).people, *([ft_hist[x]] if spec.ft_prior else []))
                             for x in ("E2024", "E2025")])
            offset = role_offset(test, n1, t.window(SEASON).people, beta, ft_now if spec.ft_prior else None)
        past = [(*history["E2025"][metric], levels["E2025"][metric], spec.carry), (*history["E2024"][metric], levels["E2024"][metric], spec.carry / 2)] if spec.carry else None
        new_pred, _, _ = shrink(s1, n1, spec, level, offset, past, test)
        old_k = OLD_K.get(OLD_METRIC_K.get(metric, ""), None)
        old_gain = np.nan
        if old_k is not None:
            old_pred, _, _ = shrink(s1, n1, Spec(spec.kind, old_k), level, None, None, test)
            old_gain = 100 * (1 - error(old_pred) / league)
        rows.append({"metrik": metric, "eski_k_kazanç": old_gain, "yeni_kazanç": 100 * (1 - error(new_pred) / league),
                     "gelecek_deneme": int(w.sum()), "koddaki": f"k={spec.k:g} rol={spec.role} w={spec.carry:g}"})
    return pd.DataFrame(rows)


def new_ratings(t: Tables) -> pd.DataFrame:
    m = add_mental_metrics(t, add_defense_metrics(t, season_metrics(t)))
    reference = fixed_reference(m)
    return pd.concat([score_fixed(g.set_index("player_id"), reference, RATING_ATTRIBUTES, PRIOR_K).assign(season=x).reset_index()
                      for x, g in m.groupby("season")], ignore_index=True), m


def old_ratings(t: Tables, games: set) -> pd.DataFrame:
    def window(season, keep=None):
        s, pg, po = t.shots[t.shots.season == season], t.player_games[t.player_games.season == season], t.possessions[t.possessions.season == season]
        if keep is not None:
            s, pg, po = s[s.gamecode.isin(keep)], pg[pg.gamecode.isin(keep)], po[po.gamecode.isin(keep)]
        return WindowData(s.copy(), pg, po)

    w = window(SEASON, games)
    priors = league_priors(w)
    carry = carry_counts([(window(x).shots, window(x).player_games, weight) for x, weight in zip(("E2025", "E2024"), CARRY_WEIGHTS)])
    m = compute_metrics(w, priors, shooter_expectation(w.shots, priors), carry=carry)
    return score(m, m[qualified(m)])


def main() -> None:
    t = load_tables()
    pg = t.window(SEASON).player_games
    first = first_half_games(pg)
    second = set(pg.gamecode) - first
    gains = metric_gains(t, first, second)

    new_first, _ = new_ratings(only_games(t, SEASON, first))
    new_first = new_first[new_first.season == SEASON].set_index("player_id")
    old_first = old_ratings(t, first)
    c2 = counts(t.window(SEASON, second))
    effects2 = {}
    poss2 = possession_table(t.window(SEASON, second))
    for name, cfg in EFFECTS.items():
        effects2[name] = -Design.build(poss2, cfg.target, cfg.use_offense, cfg.use_team).solve(cfg.lam).beta
    m1 = pg[pg.gamecode.isin(first)].groupby("player_id").minutes.sum()
    m2 = pg[pg.gamecode.isin(second)].groupby("player_id").minutes.sum()
    players = m1[m1 >= MIN_MINUTES].index.intersection(m2[m2 >= MIN_MINUTES].index)

    rows = []
    targets = {**TARGET, "rim_protection": ("rim_effect", 1), "perimeter_defense": ("three_att_effect", 1), "team_defense": ("team_effect", 1)}
    load_second = load_counts(t.window(SEASON, second))["load_minutes"]
    for key, (metric, sign) in targets.items():
        if metric in effects2:
            actual = effects2[metric]
        else:
            s, n = c2[metric]
            has = n[n > 0].index
            actual = sign * s.reindex(has).fillna(0) / n.reindex(has)
        common = players.intersection(actual.dropna().index)
        rows.append({"özellik": key, "oyuncu": len(common),
                     "eski_r": spearman(old_first.loc[common.intersection(old_first.index), key], actual.reindex(common)),
                     "yeni_r": spearman(new_first.loc[common, key], actual.reindex(common))})
    rows.append({"özellik": "stamina", "oyuncu": len(players),
                 "eski_r": spearman(old_first.loc[players, "stamina"], (load_second[0] / load_second[1]).reindex(players)),
                 "yeni_r": spearman(new_first.loc[players, "stamina"], (load_second[0] / load_second[1]).reindex(players))})
    attr = pd.DataFrame(rows)
    better = int((attr.yeni_r > attr.eski_r).sum())

    full, _ = new_ratings(t)
    people = t.people[["season", "player_id", "height", "position"]]
    meta = pg.groupby("player_id").agg(player=("player", "last"), team=("team", "last"), minutes=("minutes", "sum")).reset_index().assign(season=SEASON)
    d = meta.merge(full[full.season == SEASON], on=["season", "player_id"]).merge(people, on=["season", "player_id"], how="left")
    old = pd.read_parquet(TABLES_DIR / "ratings_season_v1.parquet")
    old = old[old.season == SEASON][["player_id", "rim_protection"]].rename(columns={"rim_protection": "eski"})
    d = d.merge(old, on="player_id")
    lists = json.loads((Path(__file__).parent / "reference_lists.json").read_text(encoding="utf-8"))["rim_protection"]
    names = [p["name"] for p in lists["best_players"]]
    enough = d[d.minutes >= 100]
    best = enough[enough.player.isin(names)]
    guards = enough[(enough.position == "Guard") & (enough.height <= 188)]
    top = enough.sort_values("rim_protection", ascending=False).head(20)
    top_old = enough.sort_values("eski", ascending=False).head(20)
    rim = pd.DataFrame([
        {"ölçüt": "Referans listen ortalaması", "eski": best.eski.mean(), "yeni": best.rim_protection.mean()},
        {"ölçüt": f"Referans listende 16+ ({len(best)} oyuncu)", "eski": int((best.eski >= 16).sum()), "yeni": int((best.rim_protection >= 16).sum())},
        {"ölçüt": f"Kısa guard ortalaması ({len(guards)} oyuncu)", "eski": guards.eski.mean(), "yeni": guards.rim_protection.mean()},
        {"ölçüt": "Kısa guardlarda 16+", "eski": int((guards.eski >= 16).sum()), "yeni": int((guards.rim_protection >= 16).sum())},
        {"ölçüt": "İlk 20'de guard", "eski": int((top_old.position == "Guard").sum()), "yeni": int((top.position == "Guard").sum())},
        {"ölçüt": "Takım payı", "eski": team_share(enough, "eski"), "yeni": team_share(enough, "rim_protection")},
    ])
    out = ["# E2026 son kontrolü\n", f"Parametre seçiminde kullanılmayan sezon. İlk {len(first)} maçtan puan, sonraki {len(second)} maç hedef. Hiçbir ayar yapılmadı.\n",
           "## 1. Özellikler: ilk yarı puanı ile ikinci yarı ölçümü\n",
           f"Spearman korelasyonu, her yarıda en az {MIN_MINUTES} dakika. Hedef her iki yöntem için de yeni tanımla ölçülür. Yeni yöntem {better}/{len(attr)} özellikte daha yüksek. "
           f"Ortalama: eski {attr.eski_r.mean():.3f}, yeni {attr.yeni_r.mean():.3f}.\n", table(attr), "",
           "## 2. Metrikler: ikinci yarıyı tahmin\n", "Lig ortalamasına göre hata azalması (%). `eski_k_kazanç`: yeni tanım, eski k, lig beklentisi.\n", table(gains), "",
           "## 3. Pota Koruma, tüm E2026 (en az 100 dakika)\n", table(rim), "",
           "**İlk 20:** " + ", ".join(f"{r.player.title()} ({r.position[0] if isinstance(r.position, str) else '?'}) {r.rim_protection}" for r in top.itertuples()), ""]
    text = "\n".join(out)
    (AUDIT_DIR / "final_check.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
