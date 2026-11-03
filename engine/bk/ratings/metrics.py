"""Per-player metrics for a time window, shrunk toward league priors.

Every metric is regressed toward the league mean with a prior strength `k`
(pseudo-observations), so small samples land near average instead of at the
extremes:  shrunk = (successes + k * league_rate) / (trials + k).

Each metric also carries its sample size so the UI can show confidence
n / (n + k).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

CLUTCH_PERIOD, CLUTCH_CLOCK, CLUTCH_MARGIN = 4, 300, 5  # last 5 min of Q4/OT, within 5 pts
LATE_STINT_SECONDS = 420  # 7+ continuous minutes on court

# metric -> prior strength k (pseudo-attempts). Shooting values were chosen by a
# month-ahead backtest (scripts/backtest.py): rim skill shows up fast, while
# mid-range and three-point percentages need ~400 attempts before they beat the
# league average as a predictor.
PRIOR_K: dict[str, float] = {
    "rim_pct": 50, "paint_pct": 100, "mid_pct": 400, "three_pct": 400, "corner3_pct": 400,
    "ft_pct": 40, "ftr": 80, "tov_pct": 100,
    "unast_rate": 300, "ast_rate": 300, "orb_rate": 300, "drb_rate": 300,
    "stl_rate": 300, "blk_rate": 300, "pf_rate": 300,
    "on_off_def": 1000, "perim_contest": 300, "rim_protect": 300,
    "clutch_resid": 40, "late_stint_resid": 80, "consistency": 8,
}


@dataclass
class WindowData:
    shots: pd.DataFrame
    player_games: pd.DataFrame
    possessions: pd.DataFrame


def _shrink_prop(made: pd.Series, att: pd.Series, p0: float, k: float) -> pd.Series:
    return (made.fillna(0) + k * p0) / (att.fillna(0) + k)


def league_priors(d: WindowData) -> dict[str, float]:
    s, pg = d.shots, d.player_games
    z = s.groupby("zone").made.mean()
    hc = s[s.context == "halfcourt"] if "context" in s else s
    hz = hc.groupby("zone").made.mean()
    poss_off = len(d.possessions)
    three = s[s.value == 3]
    fga = pg.fg2a.sum() + pg.fg3a.sum()
    return {
        "hc_rim": hz.get("rim", 0.62), "hc_paint": hz.get("paint", 0.43), "hc_mid": hz.get("mid", 0.39),
        "hc_corner3": hz.get("corner3", 0.36),
        "hc_three": hc[hc.value == 3].made.mean() if (hc.value == 3).any() else 0.35,
        "rim": z.get("rim", 0.65), "paint": z.get("paint", 0.45), "mid": z.get("mid", 0.40),
        "corner3": z.get("corner3", 0.37), "three": three.made.mean() if len(three) else 0.36,
        "ft": pg.ftm.sum() / max(pg.fta.sum(), 1),
        "ftr": pg.fta.sum() / max(fga, 1),
        "tov_pct": pg.tov.sum() / max(fga + 0.44 * pg.fta.sum() + pg.tov.sum(), 1),
        # per-100-possession rates for the average player (team totals / 5 players on court)
        "unast": 100 * (s.made & ~s.assisted).sum() / max(5 * poss_off, 1),
        "ast": 100 * pg.ast.sum() / max(5 * poss_off, 1),
        "orb": 100 * pg.orb.sum() / max(5 * poss_off, 1),
        "drb": 100 * pg.drb.sum() / max(5 * poss_off, 1),
        "stl": 100 * pg.stl.sum() / max(5 * poss_off, 1),
        "blk": 100 * pg.blk.sum() / max(5 * poss_off, 1),
        "pf": 100 * pg.pf.sum() / max(5 * poss_off, 1),
    }


def shooter_expectation(shots: pd.DataFrame, priors: dict[str, float]) -> pd.Series:
    """Expected make probability per shot from the shooter's shrunk zone percentage."""
    p0 = shots.zone.map({"rim": priors["rim"], "paint": priors["paint"], "mid": priors["mid"],
                         "corner3": priors["corner3"], "above_break3": priors["three"]}).fillna(priors["three"])
    g = shots.groupby(["player_id", "zone"]).made
    made, att = g.transform("sum"), g.transform("size")
    k = shots.zone.map({"rim": PRIOR_K["rim_pct"], "paint": PRIOR_K["paint_pct"], "mid": PRIOR_K["mid_pct"],
                        "corner3": PRIOR_K["corner3_pct"], "above_break3": PRIOR_K["three_pct"]}).fillna(200)
    return (made + k * p0) / (att + k)


def _per100(count: pd.Series, poss: pd.Series, p0_rate: float, k: float) -> pd.Series:
    """Shrunk per-100-possession rate."""
    return 100 * (count.fillna(0) + k * p0_rate / 100) / (poss.fillna(0) + k)


def _resid(df: pd.DataFrame, key: str, k: float) -> tuple[pd.Series, pd.Series]:
    g = df.groupby(key).resid
    return g.sum() / (g.size() + k), g.size()


SHOOTING_KEYS = ("rim", "paint", "mid", "corner3", "three",
                 "hc_rim", "hc_paint", "hc_mid", "hc_corner3", "hc_three", "ft")


def shooting_counts(shots: pd.DataFrame, pg: pd.DataFrame) -> pd.DataFrame:
    """Makes (<key>_m) and attempts (<key>_a) per player for every shooting metric."""
    out: dict[str, pd.Series] = {}

    def add(key: str, df: pd.DataFrame) -> None:
        g = df.groupby("player_id").made
        out[f"{key}_m"], out[f"{key}_a"] = g.sum().astype(float), g.size().astype(float)

    hc = shots[shots.context == "halfcourt"] if "context" in shots else shots
    for prefix, df in (("", shots), ("hc_", hc)):
        for z in ("rim", "paint", "mid", "corner3"):
            add(prefix + z, df[df.zone == z])
        add(prefix + "three", df[df.value == 3])
    ft = pg.groupby("player_id")[["ftm", "fta"]].sum().astype(float)
    out["ft_m"], out["ft_a"] = ft.ftm, ft.fta
    return pd.DataFrame(out).fillna(0)


def carry_counts(history: list[tuple[pd.DataFrame, pd.DataFrame, float]]) -> pd.DataFrame | None:
    """Weighted shooting counts from earlier seasons: [(shots, player_games, weight), ...].

    A season-ahead backtest showed that pooling last season's attempts at full weight
    beats both the league average and this-season-only estimates for rim, mid-range
    and three-point shooting.
    """
    parts = [shooting_counts(s, pg) * w for s, pg, w in history if len(s) and w > 0]
    if not parts:
        return None
    return pd.concat(parts).groupby(level=0).sum()


def compute_metrics(d: WindowData, priors: dict[str, float], expected: pd.Series | None = None,
                    carry: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per player with shrunk metric values and sample sizes (n_<metric>).

    `carry` adds weighted shooting attempts from earlier seasons (see carry_counts).
    """
    s, pg, po = d.shots.copy(), d.player_games, d.possessions
    s["exp"] = expected.reindex(s.index) if expected is not None else shooter_expectation(s, priors)
    s["resid"] = s.made.astype(float) - s.exp

    box = pg.groupby("player_id").agg(
        player=("player", "last"), team=("team", "last"), games=("gamecode", "size"),
        minutes=("minutes", "sum"), fg2a=("fg2a", "sum"), fg3a=("fg3a", "sum"),
        ftm=("ftm", "sum"), fta=("fta", "sum"), ast=("ast", "sum"), tov=("tov", "sum"),
        orb=("orb", "sum"), drb=("drb", "sum"), stl=("stl", "sum"), blk=("blk", "sum"),
        pf=("pf", "sum"), pts=("pts", "sum"))
    m = pd.DataFrame(index=box.index)
    m[["player", "team", "games", "minutes"]] = box[["player", "team", "games", "minutes"]]
    m["mpg"] = box.minutes / box.games

    # shooting -------------------------------------------------------------------
    # counts from this window, plus weighted counts carried over from earlier seasons
    cur = shooting_counts(s, pg)
    tot = cur.reindex(m.index).fillna(0)
    if carry is not None:
        tot = tot.add(carry.reindex(m.index).fillna(0), fill_value=0)
    for name, key, p in [("rim_pct", "rim", "rim"), ("paint_pct", "paint", "paint"), ("mid_pct", "mid", "mid"),
                         ("corner3_pct", "corner3", "corner3"), ("three_pct", "three", "three"),
                         ("hc_rim_pct", "hc_rim", "hc_rim"), ("hc_paint_pct", "hc_paint", "hc_paint"),
                         ("hc_mid_pct", "hc_mid", "hc_mid"), ("hc_corner3_pct", "hc_corner3", "hc_corner3"),
                         ("hc_three_pct", "hc_three", "hc_three"), ("ft_pct", "ft", "ft")]:
        k = PRIOR_K[name[3:] if name.startswith("hc_") else name]
        m[name] = _shrink_prop(tot[f"{key}_m"], tot[f"{key}_a"], priors[p], k)
        if not name.startswith("hc_"):
            m[f"n_{name}"] = tot[f"{key}_a"]
    fga = box.fg2a + box.fg3a
    m["ftr"] = (box.fta + PRIOR_K["ftr"] * priors["ftr"]) / (fga + PRIOR_K["ftr"])
    m["n_ftr"] = fga
    plays = fga + 0.44 * box.fta + box.tov
    m["tov_pct"] = (box.tov + PRIOR_K["tov_pct"] * priors["tov_pct"]) / (plays + PRIOR_K["tov_pct"])
    m["n_tov_pct"] = plays

    # on-court possessions --------------------------------------------------------
    off = po[["off_lineup", "points"]].explode("off_lineup").rename(columns={"off_lineup": "player_id"})
    dfn = po[["def_lineup", "points", "defense", "season", "gamecode"]].explode("def_lineup").rename(
        columns={"def_lineup": "player_id"})
    off_poss = off.groupby("player_id").size().reindex(m.index).fillna(0)
    def_poss = dfn.groupby("player_id").size().reindex(m.index).fillna(0)
    m["off_poss"], m["def_poss"] = off_poss, def_poss
    unast = s[s.made & ~s.assisted].groupby("player_id").size().reindex(m.index)
    for name, cnt, poss, p in [("unast_rate", unast, off_poss, "unast"), ("ast_rate", box.ast, off_poss, "ast"),
                               ("orb_rate", box.orb, off_poss, "orb"), ("drb_rate", box.drb, def_poss, "drb"),
                               ("stl_rate", box.stl, def_poss, "stl"), ("blk_rate", box.blk, def_poss, "blk"),
                               ("pf_rate", box.pf, def_poss, "pf")]:
        m[name] = _per100(cnt, poss, priors[p], PRIOR_K[name])
        m[f"n_{name}"] = poss

    # on/off defense: points allowed per 100 with player off minus on (positive = helps)
    team_def = po.groupby(["season", "gamecode", "defense"]).agg(pts=("points", "sum"), n=("points", "size"))
    on = dfn.groupby(["player_id", "season", "gamecode", "defense"]).agg(pts=("points", "sum"), n=("points", "size"))
    on = on.join(team_def, on=["season", "gamecode", "defense"], rsuffix="_team")
    agg = on.groupby("player_id")[["pts", "n", "pts_team", "n_team"]].sum()
    off_n = agg.n_team - agg.n
    on_rate = agg.pts / agg.n.clip(lower=1)
    off_rate = (agg.pts_team - agg.pts) / off_n.clip(lower=1)
    harmonic = (agg.n * off_n) / (agg.n + off_n).clip(lower=1)  # effective sample size of a difference
    k = PRIOR_K["on_off_def"]
    m["on_off_def"] = (100 * (off_rate - on_rate) * harmonic / (harmonic + k)).reindex(m.index).fillna(0)
    m["n_on_off_def"] = harmonic.reindex(m.index).fillna(0)

    # defender proxies: opponent make-rate vs. expectation while the player is on court
    sd = s[["def_lineup", "resid", "value", "zone"]].explode("def_lineup").rename(columns={"def_lineup": "player_id"})
    for name, mask in [("perim_contest", sd.value == 3), ("rim_protect", sd.zone.isin(["rim", "paint"]))]:
        v, n = _resid(sd[mask], "player_id", PRIOR_K[name])
        m[name] = (-v).reindex(m.index).fillna(0)  # opponents missing more than expected = positive
        m[f"n_{name}"] = n.reindex(m.index).fillna(0)

    # clutch and stamina: shooter residuals in pressure / fatigue situations
    clutch = s[(s.period >= CLUTCH_PERIOD) & (s.clock_left <= CLUTCH_CLOCK) & (s.margin_before.abs() <= CLUTCH_MARGIN)]
    v, n = _resid(clutch, "player_id", PRIOR_K["clutch_resid"])
    m["clutch_resid"], m["n_clutch_resid"] = v.reindex(m.index).fillna(0), n.reindex(m.index).fillna(0)
    v, n = _resid(s[s.stint_seconds >= LATE_STINT_SECONDS], "player_id", PRIOR_K["late_stint_resid"])
    m["late_stint_resid"], m["n_late_stint_resid"] = v.reindex(m.index).fillna(0), n.reindex(m.index).fillna(0)

    # consistency: negative spread of per-game game score per 30 min, shrunk toward the median spread
    g = pg.assign(gmsc=game_score(pg), w=pg.minutes.clip(lower=1))
    g["per30"] = 30 * g.gmsc / g.w.clip(lower=10)
    spread = g[g.minutes >= 10].groupby("player_id").per30.agg(["std", "size"])
    med = spread["std"].median()
    kk = PRIOR_K["consistency"]
    m["consistency"] = -((spread["std"].fillna(med) * spread["size"] + kk * med) / (spread["size"] + kk)).reindex(m.index).fillna(-med)
    m["n_consistency"] = spread["size"].reindex(m.index).fillna(0)
    m["n_mpg"] = box.games
    return m


def game_score(pg: pd.DataFrame) -> pd.Series:
    """Hollinger game score from a box line."""
    fgm = pg.fg2m + pg.fg3m
    fga = pg.fg2a + pg.fg3a
    return (pg.pts + 0.4 * fgm - 0.7 * fga - 0.4 * (pg.fta - pg.ftm) + 0.7 * pg.orb + 0.3 * pg.drb
            + pg.stl + 0.7 * pg.ast + 0.7 * pg.blk - 0.4 * pg.pf - pg.tov)


def game_ratings(pg: pd.DataFrame) -> pd.DataFrame:
    """Single-game performance rating on a 1–10 scale (6.6 ≈ an ordinary outing)."""
    g = pg.copy()
    g["gmsc"] = game_score(g)
    rate = g.gmsc.sum() / g.minutes.sum()
    g["resid"] = g.gmsc - rate * g.minutes
    sd = g.loc[g.minutes >= 10, "resid"].std() or 1.0
    g["game_rating"] = np.clip(6.6 + 1.1 * g.resid / sd, 3.0, 10.0).round(1)
    return g
