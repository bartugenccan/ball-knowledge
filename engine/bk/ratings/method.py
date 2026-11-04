"""Shared estimation method: prior strength from data, a fixed 1-20 scale, rating intervals.

The current scale ranks each player against the same window's already shrunk values. Early in
a season those values sit close together, so tiny gaps still spread across the whole 1-20 range.
Scoring against a fixed reference of full seasons keeps small samples near the middle: reaching
an extreme rating then takes real evidence.
"""

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

from bk.ratings.attributes import ATTRIBUTES, CENTER, SCALE, _normal_scores
from bk.ratings.metrics import PRIOR_K

REFERENCE_SEASONS = ("E2024", "E2025")
REFERENCE_MINUTES = 500
INTERVAL = 0.80
Z_INTERVAL = NormalDist().inv_cdf(0.5 + INTERVAL / 2)

LOW_DATA_PRIOR_SHARE = 3  # own data must carry at least a quarter of the estimate: n >= k / 3
SHOT_VARIANCE = 0.24   # variance of one make/miss around its expectation, near p(1-p) at p = 0.6
MPG_GAME_SD = 6.0      # game-to-game spread of a player's minutes
POINTS_VARIANCE = 1.4  # variance of points scored on one possession
FTA_PER_TRIP = 1.9     # free throws arrive in trips, so their count varies more than a Poisson count

PROPORTIONS = {"rim_pct", "paint_pct", "mid_pct", "three_pct", "corner3_pct", "ft_pct", "tov_pct"}
RATES_PER_100 = {"unast_rate", "ast_rate", "orb_rate", "drb_rate", "stl_rate", "blk_rate", "pf_rate"}
SHOT_RESIDUALS = {"perim_contest", "rim_protect", "clutch_resid", "late_stint_resid"}
LEAGUE_LEVEL = {"rim_pct": "rim", "paint_pct": "paint", "mid_pct": "mid", "corner3_pct": "corner3", "three_pct": "three",
                "ft_pct": "ft", "ftr": "ftr", "tov_pct": "tov_pct", "unast_rate": "unast", "ast_rate": "ast",
                "orb_rate": "orb", "drb_rate": "drb", "stl_rate": "stl", "blk_rate": "blk", "pf_rate": "pf"}


def estimate_k(x: np.ndarray, n: np.ndarray, noise_variance: float) -> float:
    """Prior strength by the method of moments: sampling noise over true between-player variance.

    x is each player's observed rate, n its number of trials and noise_variance the variance of
    one trial. Returns infinity when observed differences do not exceed what chance alone gives,
    which means the data show no stable difference between players.
    """
    keep = n > 0
    x, n = np.asarray(x, dtype=float)[keep], np.asarray(n, dtype=float)[keep]
    total = n.sum()
    mean = (n * x).sum() / total
    between = (n * (x - mean) ** 2).sum()
    true_variance = (between - (len(x) - 1) * noise_variance) / (total - (n**2).sum() / total)
    return float(noise_variance / true_variance) if true_variance > 0 else float("inf")


def metric_se(m: pd.DataFrame, metric: str, k: float | None = None) -> pd.Series:
    """Standard error of a metric's shrunk estimate, in the metric's own units."""
    if f"se_{metric}" in m:
        return m[f"se_{metric}"].astype(float)
    k = PRIOR_K.get(metric, 10.0) if k is None else k
    value = m[metric].astype(float)
    n = m.get(f"n_{metric}", pd.Series(0.0, index=m.index)).astype(float).fillna(0)
    if metric in PROPORTIONS:
        return np.sqrt((value * (1 - value)).clip(lower=0) / (n + k))
    if metric == "ftr":
        return np.sqrt(FTA_PER_TRIP * value.clip(lower=0) / (n + k))
    if metric in RATES_PER_100:
        return 100 * np.sqrt((value / 100).clip(lower=0) / (n + k))
    if metric in SHOT_RESIDUALS:
        return np.sqrt(SHOT_VARIANCE / (n + k))
    if metric == "on_off_def":
        return 100 * np.sqrt(POINTS_VARIANCE / (n + k))
    if metric == "mpg":
        return MPG_GAME_SD / np.sqrt(n.clip(lower=1))
    if metric == "consistency":
        return value.abs() / np.sqrt(2 * (n + k))
    raise KeyError(f"no standard error defined for {metric}")


def fixed_reference(metrics: pd.DataFrame, seasons=REFERENCE_SEASONS, minutes: float = REFERENCE_MINUTES) -> pd.DataFrame:
    """Full-season player rows that define the scale: same seasons and threshold for every window."""
    return metrics[metrics.season.isin(seasons) & (metrics.minutes >= minutes)]


def center_on_league(m: pd.DataFrame, priors: dict[str, float], base: dict[str, float]) -> pd.DataFrame:
    """Express each metric relative to its window's league level, on the base level's scale.

    Without this, a window whose league mid-range % happens to run high would lift everyone
    above the reference. A rating says how a player compares with the league at that time.
    """
    out = m.copy()
    for metric, key in LEAGUE_LEVEL.items():
        if metric in out:
            out[metric] = out[metric] - priors[key] + base[key]
    return out


def average_priors(priors: list[dict[str, float]]) -> dict[str, float]:
    return {k: float(np.mean([p[k] for p in priors])) for k in priors[0]}


def _clip_round(z: pd.Series) -> pd.Series:
    return np.clip(np.round(CENTER + SCALE * z), 1, 20).astype(int)


def low_data(m: pd.DataFrame, components, prior_k: dict[str, float]) -> pd.Series:
    """True when a player's own data carry under a quarter of the estimate (n < k/3) in some component."""
    out = pd.Series(False, index=m.index)
    for metric, _, _ in components:
        if metric in prior_k:
            out |= m.get(f"n_{metric}", pd.Series(0.0, index=m.index)).astype(float).fillna(0) < prior_k[metric] / LOW_DATA_PRIOR_SHARE
    return out


def score_fixed(m: pd.DataFrame, reference: pd.DataFrame, attributes=ATTRIBUTES,
                prior_k: dict[str, float] = PRIOR_K) -> pd.DataFrame:
    """Rating, 80% interval and low-data flag per attribute against a fixed reference.

    Each component's interval goes through the same percentile mapping as its estimate.
    Components are combined assuming independent errors. Columns: <attr>, <attr>_lo,
    <attr>_hi and <attr>_low_data.
    """
    out = pd.DataFrame(index=m.index)
    for a in attributes:
        z_mid = pd.Series(0.0, index=m.index)
        var_lo = pd.Series(0.0, index=m.index)
        var_hi = pd.Series(0.0, index=m.index)
        ref_z = pd.Series(0.0, index=reference.index)
        for metric, weight, sign in a.components:
            ref = reference[metric].to_numpy(dtype=float)
            ref_z += weight * sign * _normal_scores(reference[metric], ref)
            value, se = m[metric].astype(float), metric_se(m, metric)
            z = _normal_scores(value, ref)
            below = _normal_scores(value - Z_INTERVAL * se, ref)
            above = _normal_scores(value + Z_INTERVAL * se, ref)
            z_mid += weight * sign * z
            down, up = (z - below, above - z) if sign > 0 else (above - z, z - below)
            var_lo += (weight * down) ** 2
            var_hi += (weight * up) ** 2
        sd = ref_z.std() or 1.0
        out[a.key] = _clip_round(z_mid / sd)
        out[f"{a.key}_lo"] = _clip_round((z_mid - np.sqrt(var_lo)) / sd)
        out[f"{a.key}_hi"] = _clip_round((z_mid + np.sqrt(var_hi)) / sd)
        out[f"{a.key}_low_data"] = low_data(m, a.components, prior_k)
    return out
