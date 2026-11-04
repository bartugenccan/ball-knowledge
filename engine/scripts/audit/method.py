"""Stage 2 audit: prior strength, fixed scale and intervals, next to today's ratings.

    uv run python scripts/audit/method.py

Read-only: writes only under data/audit/, production ratings stay untouched. Metrics keep their
current definitions, except that cleaning flags are applied in the prior-strength tests. New
definitions come in later stages and will be re-tested then. E2026 is never used to choose a
parameter; it is held back as the final check.
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
from bk.ratings.attributes import ATTRIBUTES, qualified, score  # noqa: E402
from bk.ratings.legacy_build import CARRY_WEIGHTS  # noqa: E402
from bk.ratings.method import (POINTS_VARIANCE, SHOT_VARIANCE, Z_INTERVAL, average_priors,  # noqa: E402
                               center_on_league, estimate_k, fixed_reference, score_fixed)
from bk.ratings.metrics import (CLUTCH_CLOCK, CLUTCH_MARGIN, CLUTCH_PERIOD, LATE_STINT_SECONDS, PRIOR_K,  # noqa: E402
                                WindowData, carry_counts, compute_metrics, league_priors, shooter_expectation)

K_GRID = (10, 20, 40, 80, 150, 300, 600, 1000, 2000, 4000, 8000, 1e9)
CARRY_GRID = (0.0, 0.25, 0.5, 1.0)
SNAPSHOT_GAMES = 90        # matches how much of E2026 has been played
SNAPSHOT_MIN_MINUTES = 60
FINAL_MIN_MINUTES = 500
LOW_DATA_WIDTH = 8  # the first low-data rule tested, replaced by n < k
SPLIT_MIN_TRIALS = 15
MIN_CHECK_PLAYERS = 30
REF_SEASONS = ("E2024", "E2025")
WATCH = ["CROWDER", "LEDAY", "BUTKEVICIUS", "FRANCISCO", "THOMPSON, DARIUS", "TAVARES", "BROOKS, ARMONI", "OBST"]
FT_PRIOR_METRICS = {"three_pct", "mid_pct", "corner3_pct"}


def read(name: str) -> pd.DataFrame:
    return pd.read_parquet(TABLES_DIR / f"{name}.parquet")


def explode_lineups(po: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    off = po.off_lineup.explode().value_counts()
    dfn = po.def_lineup.explode().value_counts()
    return off, dfn


def window_counts(d: WindowData) -> dict[str, tuple[pd.Series, pd.Series, str]]:
    """metric -> (successes, trials, kind) per player, with the cleaning flags applied."""
    s, pg, po = d.shots, d.player_games, d.possessions
    box = pg.groupby("player_id")[["ftm", "fta", "ast", "tov", "orb", "drb", "stl", "blk", "pf", "fg2a", "fg3a"]].sum()
    off, dfn = explode_lineups(po)
    fga = box.fg2a + box.fg3a
    out: dict[str, tuple[pd.Series, pd.Series, str]] = {}

    def shots(name: str, mask: pd.Series) -> None:
        g = s[mask].groupby("player_id").made
        out[name] = (g.sum().astype(float), g.size().astype(float), "prop")

    shots("three_pct", (s.value == 3) & ~s.is_heave)
    shots("corner3_pct", s.zone_group == "corner3")
    shots("mid_pct", s.zone_group == "mid")
    shots("inside_pct", s.zone_group == "inside")
    out["ft_pct"] = (box.ftm.astype(float), box.fta.astype(float), "prop")
    out["tov_pct"] = (box.tov.astype(float), (fga + 0.44 * box.fta + box.tov).astype(float), "prop")
    out["ftr"] = (box.fta.astype(float), fga.astype(float), "rate")
    unast = s[s.made & ~s.assisted].groupby("player_id").size().astype(float)
    for name, count, trials in (("unast_rate", unast, off), ("ast_rate", box.ast, off), ("orb_rate", box.orb, off),
                                ("drb_rate", box.drb, dfn), ("stl_rate", box.stl, dfn), ("blk_rate", box.blk, dfn),
                                ("pf_rate", box.pf, dfn)):
        out[name] = (count.astype(float), trials.astype(float), "rate")

    def residual(name: str, mask: pd.Series, by_defense: bool) -> None:
        rows = s[mask]
        if by_defense:
            rows = rows[["def_lineup", "resid"]].explode("def_lineup").rename(columns={"def_lineup": "player_id"})
        g = rows.groupby("player_id").resid
        sign = -1.0 if by_defense else 1.0
        out[name] = (sign * g.sum(), g.size().astype(float), "resid")

    residual("perim_contest", (s.value == 3) & ~s.is_heave, True)
    residual("rim_protect", s.zone_group == "inside", True)
    clutch = (s.period >= CLUTCH_PERIOD) & (s.clock_left <= CLUTCH_CLOCK) & (s.margin_before.abs() <= CLUTCH_MARGIN)
    residual("clutch_resid", clutch, False)
    residual("late_stint_resid", s.stint_seconds >= LATE_STINT_SECONDS, False)

    team = po.groupby(["season", "gamecode", "defense"]).agg(pts=("points", "sum"), n=("points", "size"))
    on = (po[["def_lineup", "points", "defense", "season", "gamecode"]].explode("def_lineup")
          .groupby(["def_lineup", "season", "gamecode", "defense"]).agg(pts=("points", "sum"), n=("points", "size")))
    on = (on.join(team.add_suffix("_team"), on=["season", "gamecode", "defense"])
          .groupby(level=0)[["pts", "n", "pts_team", "n_team"]].sum())
    off_n = (on.n_team - on.n).clip(lower=0)
    harmonic = (on.n * off_n / (on.n + off_n).clip(lower=1)).astype(float)
    diff = on.pts / on.n.clip(lower=1) - (on.pts_team - on.pts) / off_n.clip(lower=1)
    out["on_off_def"] = (-diff * harmonic, harmonic, "points")
    return out


def noise(kind: str, mean: float) -> float:
    return {"prop": mean * (1 - mean), "rate": mean, "resid": SHOT_VARIANCE, "points": POINTS_VARIANCE}[kind]


def halves(d: WindowData) -> tuple[WindowData, WindowData]:
    """Split a season at the median game date: the first half predicts the second."""
    dates = d.player_games.groupby("gamecode").date.first().sort_values()
    first = set(dates.index[: len(dates) // 2])

    def cut(df: pd.DataFrame, keep: bool) -> pd.DataFrame:
        return df[df.gamecode.isin(first) == keep]

    return (WindowData(cut(d.shots, True), cut(d.player_games, True), cut(d.possessions, True)),
            WindowData(cut(d.shots, False), cut(d.player_games, False), cut(d.possessions, False)))


def role_prior_fit(fit: tuple, people: pd.DataFrame, ft: pd.Series, use_ft: bool) -> np.ndarray | None:
    """Weighted regression of a full season's rate on height, position and optionally FT%."""
    s_, n_, _ = fit
    d = pd.DataFrame({"s": s_, "n": n_}).dropna()
    d = d[d.n > 0].join(people[["height", "position"]]).dropna(subset=["height", "position"])
    if len(d) < 30:
        return None
    return np.linalg.lstsq(*_design(d, ft, use_ft, weight=True), rcond=None)[0]


def _design(d: pd.DataFrame, ft: pd.Series, use_ft: bool, weight: bool):
    parts = [np.ones(len(d)), d.height.to_numpy(float), (d.position == "Center").to_numpy(float),
             (d.position == "Forward").to_numpy(float)]
    if use_ft:
        parts.append(ft.reindex(d.index).fillna(ft.mean()).to_numpy(float))
    x = np.column_stack(parts)
    if not weight:
        return x
    w = np.sqrt(d.n.to_numpy(float))
    return x * w[:, None], (d.s / d.n).to_numpy(float) * w


def mse(pred: pd.Series, x2: pd.Series, n2: pd.Series) -> float:
    return float((n2 * (x2 - pred) ** 2).sum() / n2.sum())


def prior_strength_table(season_windows: dict[str, WindowData], people: pd.DataFrame) -> pd.DataFrame:
    """Evaluate every prior strength on the second half of E2024 and E2025."""
    full = {s: window_counts(w) for s, w in season_windows.items()}
    split = {s: tuple(window_counts(h) for h in halves(w)) for s, w in season_windows.items()}
    rows = []
    for metric, (_, _, kind) in full["E2025"].items():
        pooled_x, pooled_n = [], []
        for season in full:
            s_, n_, _ = full[season][metric]
            has = n_[n_ > 0].index
            pooled_x.append(s_.reindex(has).fillna(0) / n_.reindex(has))
            pooled_n.append(n_.reindex(has))
        x_all, n_all = pd.concat(pooled_x).to_numpy(), pd.concat(pooled_n).to_numpy()
        mean = float((x_all * n_all).sum() / n_all.sum())
        k_moment = estimate_k(x_all, n_all, noise(kind, mean))

        def eval_halves(season: str, k: float, mu=None, w: float = 0.0) -> float:
            (s1, n1, _), (s2, n2, _) = split[season][0][metric], split[season][1][metric]
            test = n2[n2 > 0].index
            base = float(s1.sum() / n1.sum())
            prior = pd.Series(base, index=test) if mu is None else mu.reindex(test).fillna(base)
            past_s = past_n = 0.0
            if w > 0:
                ps, pn, _ = full["E2024"][metric]
                past_s, past_n = w * ps.reindex(test).fillna(0), w * pn.reindex(test).fillna(0)
            pred = (s1.reindex(test).fillna(0) + past_s + k * prior) / (n1.reindex(test).fillna(0) + past_n + k)
            x2 = (s2.reindex(test) / n2.reindex(test))
            league = mse(pd.Series(base, index=test), x2, n2.reindex(test))
            return 100 * (1 - mse(pred, x2, n2.reindex(test)) / league)

        gains = {k: np.mean([eval_halves(s, k) for s in full]) for k in K_GRID}
        best_k = max(gains, key=gains.get)
        current_key = "rim_protect" if metric == "inside_pct" else metric
        current_k = PRIOR_K.get(current_key, 100) if metric != "inside_pct" else 100
        current_gain = float(np.mean([eval_halves(s, current_k) for s in full]))

        # role prior and carry, E2025 only: the fit uses E2024, so E2025 stays out of sample
        base25_gain = max(eval_halves("E2025", k) for k in K_GRID)
        pe25 = people[people.season == "E2025"].set_index("player_id")
        pe24 = people[people.season == "E2024"].set_index("player_id")
        ft24 = (full["E2024"]["ft_pct"][0] / full["E2024"]["ft_pct"][1].clip(lower=20))
        ft1 = split["E2025"][0]["ft_pct"][0] / split["E2025"][0]["ft_pct"][1].clip(lower=20)
        use_ft = metric in FT_PRIOR_METRICS
        beta = role_prior_fit(full["E2024"][metric], pe24, ft24, use_ft)
        mu = None
        if beta is not None:
            s1, n1, _ = split["E2025"][0][metric]
            base = float(s1.sum() / n1.sum())
            pop = pe25[["height", "position"]].dropna()
            pred = pd.Series(_design(pop, ft1, use_ft, weight=False) @ beta, index=pop.index)
            trials = n1.reindex(pop.index).fillna(0)
            # keep the fitted differences between players, take the level from this season's data
            mu = pred - (pred * trials).sum() / max(trials.sum(), 1) + base
        finite = [k for k in K_GRID if k < 1e9]
        role_gain = max(eval_halves("E2025", k, mu) for k in finite) if mu is not None else np.nan
        weights = CARRY_GRID if kind in ("prop", "rate") else (0.0,)
        carry_gain = {w: max(eval_halves("E2025", k, None, w) for k in K_GRID) for w in weights}
        both = {(k, w): eval_halves("E2025", k, mu, w) for k in finite for w in weights} if mu is not None else {}
        best_pair = max(both, key=both.get) if both else (None, None)
        best_w = max(carry_gain, key=carry_gain.get)

        # interval check on the second half, using the best league-prior strength
        hits, total = [], []
        for season in full:
            (s1, n1, _), (s2, n2, _) = split[season][0][metric], split[season][1][metric]
            test = n2[n2 >= SPLIT_MIN_TRIALS].index
            base = float(s1.sum() / n1.sum())
            k_use = min(best_k, 1e6)
            nn1 = n1.reindex(test).fillna(0)
            theta = (s1.reindex(test).fillna(0) + k_use * base) / (nn1 + k_use)
            x2 = s2.reindex(test) / n2.reindex(test)
            if kind == "prop":
                var = theta * (1 - theta)
            elif kind == "rate":
                var = theta.clip(lower=1e-6)
            else:
                var = pd.Series(noise(kind, base), index=test)
            se = np.sqrt(var / n2.reindex(test) + var / (nn1 + k_use))
            hits.append(((x2 - theta).abs() <= Z_INTERVAL * se).sum())
            total.append(len(test))
        cover = sum(hits) / sum(total) if sum(total) >= MIN_CHECK_PLAYERS else np.nan

        # split-half reliability among players with enough trials in both halves
        rs = []
        for season in full:
            (s1, n1, _), (s2, n2, _) = split[season][0][metric], split[season][1][metric]
            ok = n1.index.intersection(n2.index)
            ok = ok[(n1.reindex(ok) >= SPLIT_MIN_TRIALS) & (n2.reindex(ok) >= SPLIT_MIN_TRIALS)]
            if len(ok) >= MIN_CHECK_PLAYERS:
                rs.append((s1.reindex(ok) / n1.reindex(ok)).corr(s2.reindex(ok) / n2.reindex(ok)))
        rows.append({"metrik": metric, "k_şimdi": current_k,
                     "k_moment": round(k_moment) if np.isfinite(k_moment) else "sonsuz",
                     "k_test": ("sonsuz" if best_k >= 1e9 else int(best_k)), "kazanç_şimdi": current_gain,
                     "kazanç_k_test": gains[best_k], "E25_yalın": base25_gain, "E25_rol": role_gain,
                     "E25_geçmiş": carry_gain[best_w], "geçmiş_w": best_w,
                     "E25_ikisi": both[best_pair] if both else np.nan, "ikisi_k": best_pair[0] if both else "-",
                     "ikisi_w": best_pair[1] if both else "-", "aralık_kapsama": cover,
                     "yarı_r": float(np.mean(rs)) if rs else np.nan})
    return pd.DataFrame(rows)


def centered(metrics: pd.DataFrame, priors: dict[str, dict], base: dict) -> pd.DataFrame:
    return pd.concat(center_on_league(m, priors[season], base) for season, m in metrics.groupby("season"))


def scale_compare(metrics: pd.DataFrame, reference: pd.DataFrame, current: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for season, m in metrics.groupby("season"):
        m = m.set_index("player_id")
        frames.append(score_fixed(m, reference).assign(season=season).reset_index())
    new = pd.concat(frames)
    return current.merge(new, on=["season", "player_id"], suffixes=("_old", ""))


def enough_by_sample(m: pd.DataFrame, a, k_table: dict[str, float]) -> pd.Series:
    """Alternative low-data rule: the player's own data outweigh the prior (n >= k) in every component."""
    ok = pd.Series(True, index=m.index)
    for metric, _, _ in a.components:
        k = k_table.get("inside_pct" if metric in ("rim_pct", "paint_pct") else metric)
        if k is not None:
            ok &= m[f"n_{metric}"].fillna(0) >= k
    return ok


def scale_summary(j: pd.DataFrame, metrics: pd.DataFrame, k_table: dict[str, float]) -> pd.DataFrame:
    rows = []
    q26 = j[(j.season == "E2026") & j.qualified]
    q25 = j[(j.season == "E2025") & j.qualified]
    m = metrics.set_index(["season", "player_id"])
    for a in ATTRIBUTES:
        k = a.key
        width = q25[f"{k}_hi"] - q25[f"{k}_lo"]
        rows.append({"özellik": k, "E2025_SD_eski": q25[f"{k}_old"].std(), "E2025_SD_yeni": q25[k].std(),
                     "E2026_SD_eski": q26[f"{k}_old"].std(), "E2026_SD_yeni": q26[k].std(),
                     "E2026_18+_eski": int((q26[f"{k}_old"] >= 18).sum()), "E2026_18+_yeni": int((q26[k] >= 18).sum()),
                     "E2025_aralık": width.mean(), "E2026_aralık": (q26[f"{k}_hi"] - q26[f"{k}_lo"]).mean(),
                     "E2025_az_veri": (width > LOW_DATA_WIDTH).mean(),
                     "E2026_az_veri": ((q26[f"{k}_hi"] - q26[f"{k}_lo"]) > LOW_DATA_WIDTH).mean(),
                     "E2025_n<k": 1 - enough_by_sample(m.loc[list(zip(q25.season, q25.player_id))], a, k_table).mean(),
                     "E2026_n<k": 1 - enough_by_sample(m.loc[list(zip(q26.season, q26.player_id))], a, k_table).mean()})
    return pd.DataFrame(rows)


def snapshot_test(d: WindowData, metrics: pd.DataFrame) -> pd.DataFrame:
    """Does a rating after 90 games point to the season-end rating? The scale uses E2024 only."""
    dates = d.player_games[d.player_games.season == "E2025"].groupby("gamecode").date.first().sort_values()
    early = set(dates.index[:SNAPSHOT_GAMES])

    def at(season: str, games: set | None = None) -> WindowData:
        out = []
        for df in (d.shots, d.player_games, d.possessions):
            x = df[df.season == season]
            out.append(x if games is None else x[x.gamecode.isin(games)])
        return WindowData(*out)

    window = at("E2025", early)
    priors = league_priors(window)
    history = at("E2024")
    carry = carry_counts([(history.shots, history.player_games, CARRY_WEIGHTS[0])])
    snap = compute_metrics(window, priors, shooter_expectation(window.shots, priors), carry=carry)
    base = league_priors(at("E2024"))
    raw_snap, raw_final = snap, metrics[metrics.season == "E2025"].set_index("player_id")
    final = center_on_league(raw_final, league_priors(at("E2025")), base)
    ref = fixed_reference(center_on_league(metrics[metrics.season == "E2024"], base, base), seasons=("E2024",))
    snap = center_on_league(snap, priors, base)

    old_early = score(raw_snap, raw_snap[qualified(raw_snap)])
    old_final = score(raw_final, raw_final[qualified(raw_final)])
    new_early = score_fixed(snap, ref)
    new_final = score_fixed(final, ref)
    keep = snap.index[snap.minutes >= SNAPSHOT_MIN_MINUTES].intersection(final.index[final.minutes >= FINAL_MIN_MINUTES])
    rows = []
    for a in ATTRIBUTES:
        k = a.key
        oe, of, ne, nf = (x.loc[keep, k] for x in (old_early, old_final, new_early, new_final))
        hit_old = (of[oe >= 18] >= 16).mean() if (oe >= 18).any() else np.nan
        hit_new = (nf[ne >= 18] >= 16).mean() if (ne >= 18).any() else np.nan
        lo, hi = new_early.loc[keep, f"{k}_lo"], new_early.loc[keep, f"{k}_hi"]
        rows.append({"özellik": k, "sapma_eski": (oe - of).abs().mean(), "sapma_yeni": (ne - nf).abs().mean(),
                     "erken_18+_eski": int((oe >= 18).sum()), "kalan_16+_eski": hit_old,
                     "erken_18+_yeni": int((ne >= 18).sum()), "kalan_16+_yeni": hit_new,
                     "aralık_son_puanı_kapsıyor": ((nf >= lo) & (nf <= hi)).mean()})
    out = pd.DataFrame(rows)
    out.attrs["players"] = len(keep)
    return out


def reference_check(j: pd.DataFrame, metrics: pd.DataFrame, people: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    lists = json.loads((Path(__file__).parent / "reference_lists.json").read_text(encoding="utf-8"))["rim_protection"]
    names = [p["name"] for p in lists["best_players"]]
    d = j.merge(people[["season", "player_id", "height", "position"]], on=["season", "player_id"], how="left")
    best = d[d.player.isin(names)].sort_values(["player", "season"])
    cols = ["season", "player", "team", "height", "minutes", "rim_protection_old", "rim_protection",
            "rim_protection_lo", "rim_protection_hi", "rim_protection_low_data"]
    rule = lists["worst_rule"]
    guards = d[(d.position == rule["position"]) & (d.height <= rule["max_height_cm"]) & (d.minutes >= rule["min_minutes"])]
    summary = {"short_guards": len(guards), "guards_mean_old": guards.rim_protection_old.mean(),
               "guards_mean_new": guards.rim_protection.mean(), "guards_max_old": int(guards.rim_protection_old.max()),
               "guards_max_new": int(guards.rim_protection.max())}
    enough = best[best.minutes >= 250]
    summary["best_n"] = len(enough)
    summary["best_mean_old"] = enough.rim_protection_old.mean()
    summary["best_mean_new"] = enough.rim_protection.mean()
    summary["top_old"] = int(guards[guards.rim_protection_old >= 16].shape[0])
    summary["top_new"] = int(guards[guards.rim_protection >= 16].shape[0])
    return best[cols], guards.sort_values("rim_protection", ascending=False)[["season", "player", "height", "minutes", "rim_protection_old", "rim_protection"]].head(8), summary


def main() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    s, pg, po = read("shots"), read("player_games"), read("possessions")
    people, metrics, ratings = read("people"), read("player_metrics_v1"), read("ratings_season_v1")

    windows = {}
    priors = {}
    for season in ("E2024", "E2025", "E2026"):
        w = WindowData(s[s.season == season].copy(), pg[pg.season == season], po[po.season == season])
        priors[season] = league_priors(w)
        if season != "E2026":  # E2026 stays out of every parameter choice
            w.shots["resid"] = w.shots.made.astype(float) - shooter_expectation(w.shots, priors[season])
            windows[season] = w
    prior = prior_strength_table(windows, people)
    prior.to_csv(AUDIT_DIR / "prior_strength.csv", index=False)
    k_table = {r.metrik: (float("inf") if r.k_test == "sonsuz" else float(r.k_test)) for r in prior.itertuples()}

    base = average_priors([priors[x] for x in REF_SEASONS])
    adjusted = centered(metrics, priors, base)
    reference = fixed_reference(adjusted)
    j = scale_compare(adjusted, reference, ratings)
    keep = ["season", "player_id", "player", "team", "games", "minutes", "qualified"]
    long_rows = []
    for a in ATTRIBUTES:
        k = a.key
        long_rows.append(j[keep].assign(attribute=k, old=j[f"{k}_old"], new=j[k], lo=j[f"{k}_lo"], hi=j[f"{k}_hi"],
                                        low_data=j[f"{k}_low_data"], old_conf=j[f"{k}_conf"]))
    pd.concat(long_rows).to_csv(AUDIT_DIR / "ratings_old_vs_new.csv", index=False)

    summary = scale_summary(j, metrics, k_table)
    snap = snapshot_test(WindowData(s, pg, po), metrics)
    best, guards, ref_sum = reference_check(j, metrics, people)

    out = ["# Aşama 2: Yöntem denetimi\n",
           f"Referans: E2024+E2025, en az 500 dakika, {len(reference)} oyuncu-sezon. Üretim puanları değişmedi. "
           "Metrik tanımları bugünkü haliyle; yeni tanımlar sonraki aşamalarda sınanacak.\n",
           "## 1. Küçültme gücü (k)\n",
           "Kazanç: sezonun ilk yarısından ikinci yarısını tahminde, lig ortalamasına göre hata azalması (%). "
           "Pozitif, oyuncuyu ayırt etmenin işe yaradığını gösterir. `k_moment` yalnızca veriden hesaplanan değer, `k_test` "
           "ikinci yarıda en iyi çıkan değer. `sonsuz`: lig ortalamasını kullanmak en iyisi, yani bu metrikte kalıcı "
           "oyuncu farkı görülmüyor. `kazanç_*` iki sezonun ortalaması. `E25_*` yalnızca E2025: yalın (k), rol (boy, pozisyon), "
           "geçmiş (E2024 sayıları), ikisi birlikte. `aralık_kapsama` %80 hedefler. `yarı_r`: iki yarının korelasyonu, "
           "yarı başına en az 15 deneme.\n",
           table(prior), "",
           "## 2. Ölçek: eski ve yeni\n",
           "Eski ölçek her sezonu kendi içinde sıralar, yeni ölçek sabit referansa bakar.\n",
           table(summary), "",
           f"`az_veri`: aralık genişliği {LOW_DATA_WIDTH} puanı aşan oyuncu payı. `n<k`: alternatif kural, oyuncunun kendi verisi "
           "beklentiden az olan oyuncu payı (k_test ile).\n",
           f"## 3. Sezon başı testi (E2025, ilk {SNAPSHOT_GAMES} maç, {snap.attrs['players']} oyuncu)\n",
           "`sapma`: erken puan ile sezon sonu puanı arasındaki ortalama fark. Yeni ölçekte referans yalnızca E2024. "
           "`kalan_16+`: erken dönemde 18+ alanların sezon sonunda 16+ kalma oranı.\n",
           table(snap), "",
           "## 4. Pota Koruma referans listesi (formül henüz eski)\n",
           table(best), "",
           f"Listeden en az 250 dakikalık {ref_sum['best_n']} oyuncu-sezonun ortalaması: eski {ref_sum['best_mean_old']:.1f}, yeni {ref_sum['best_mean_new']:.1f}. "
           f"Kısa guardlar ({ref_sum['short_guards']} oyuncu-sezon) ortalaması: eski {ref_sum['guards_mean_old']:.1f}, yeni {ref_sum['guards_mean_new']:.1f}; "
           f"16+ alan: eski {ref_sum['top_old']}, yeni {ref_sum['top_new']}.\n",
           "**En yüksek puanlı kısa guardlar:**\n", table(guards), "",
           "## 5. İzlenen oyuncular\n"]
    watch = j[j.player.str.contains("|".join(WATCH), case=False) & (j.minutes >= 100)].sort_values(["player", "season"])
    out += [table(watch[["season", "player", "minutes", "three_point_old", "three_point", "three_point_lo", "three_point_hi",
                         "rim_protection_old", "rim_protection", "rim_protection_lo", "rim_protection_hi"]]), "",
            "Tüm oyuncular ve özellikler: `ratings_old_vs_new.csv`.\n"]
    text = "\n".join(out)
    (AUDIT_DIR / "method.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
