"""Map shrunk metrics to 1–20 attributes.

Scale: every metric is converted to a normal score against the season's
reference population (qualified players), components are averaged, and the
result is mapped to CENTER + SCALE·z, clipped to [1, 20]. EuroLeague is an
elite league, so the average rotation player sits around 11–12, the league's
best in a skill reaches ~20 and the weakest lands near 3, not 1.

Month windows are scored against the *season* reference, so a month rating
lives on the same scale as the season rating (with fewer extremes because
small samples are shrunk harder, which is the honest outcome).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd

from bk.ratings.metrics import PRIOR_K

_N = NormalDist()
CENTER, SCALE = 11.5, 3.2


@dataclass(frozen=True)
class Attribute:
    key: str
    label: str        # Turkish UI label
    group: str        # hucum | savunma | zihinsel
    source: str       # veri | turetilmis | tahmini
    components: tuple[tuple[str, float, int], ...]  # (metric, weight, +1 higher-better / -1 lower-better)
    description: str = ""


ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute("finishing", "Bitiricilik", "hucum", "veri", (("rim_pct", .7, 1), ("paint_pct", .3, 1)),
              "Pota altı ve boyalı alan isabeti"),
    Attribute("mid_range", "Orta Mesafe", "hucum", "veri", (("mid_pct", 1, 1),), "Boyalı alan dışı ikilikler"),
    Attribute("three_point", "Üçlük", "hucum", "veri", (("three_pct", 1, 1),), "Tüm üçlükler"),
    Attribute("corner_three", "Köşe Üçlük", "hucum", "veri", (("corner3_pct", 1, 1),), "Köşeden üçlük"),
    Attribute("free_throw", "Serbest Atış", "hucum", "veri", (("ft_pct", 1, 1),), "Serbest atış yüzdesi"),
    Attribute("shot_creation", "Şut Yaratma", "hucum", "turetilmis", (("unast_rate", 1, 1),),
              "Asistsiz isabet / 100 hücum (kendi yarattığı şut)"),
    Attribute("passing", "Pas", "hucum", "veri", (("ast_rate", 1, 1),), "Asist / 100 hücum"),
    Attribute("ball_security", "Top Güvenliği", "hucum", "veri", (("tov_pct", 1, -1),), "Top kaybı oranı (düşük iyi)"),
    Attribute("drawing_fouls", "Faul Alma", "hucum", "veri", (("ftr", 1, 1),), "Serbest atış / şut oranı"),
    Attribute("off_rebounding", "Hücum Ribaundu", "hucum", "veri", (("orb_rate", 1, 1),), "HR / 100 hücum"),
    Attribute("def_rebounding", "Savunma Ribaundu", "savunma", "veri", (("drb_rate", 1, 1),), "SR / 100 savunma"),
    Attribute("steals", "Top Çalma", "savunma", "veri", (("stl_rate", 1, 1),), "Top çalma / 100 savunma"),
    Attribute("shot_blocking", "Blok", "savunma", "veri", (("blk_rate", 1, 1),), "Blok / 100 savunma"),
    Attribute("rim_protection", "Pota Koruma", "savunma", "tahmini", (("rim_protect", .6, 1), ("blk_rate", .4, 1)),
              "Sahadayken rakibin pota çevresi isabeti beklentinin ne kadar altında"),
    Attribute("perimeter_defense", "Çevre Savunması", "savunma", "tahmini", (("perim_contest", 1, 1),),
              "Sahadayken rakibin üçlük isabeti beklentinin ne kadar altında (contest vekili)"),
    Attribute("discipline", "Faul Disiplini", "savunma", "veri", (("pf_rate", 1, -1),), "Faul / 100 savunma (düşük iyi)"),
    Attribute("team_defense", "Savunma Etkisi", "savunma", "turetilmis", (("on_off_def", 1, 1),),
              "Sahadayken ve kenardayken yenen sayı farkı (on/off)"),
    Attribute("clutch", "Clutch", "zihinsel", "turetilmis", (("clutch_resid", 1, 1),),
              "Son 5 dk, fark ≤5: beklentiye göre isabet"),
    Attribute("stamina", "Dayanıklılık", "zihinsel", "turetilmis", (("mpg", .5, 1), ("late_stint_resid", .5, 1)),
              "Dakika yükü ve 7+ dk kesintisiz oynarken isabet"),
    Attribute("consistency", "İstikrar", "zihinsel", "turetilmis", (("consistency", 1, 1),),
              "Maçtan maça performans dalgalanması (düşük dalga iyi)"),
)

ATTR_BY_KEY = {a.key: a for a in ATTRIBUTES}


def _normal_scores(values: pd.Series, reference: np.ndarray) -> pd.Series:
    """Percentile of each value within the sorted reference, as a normal z-score."""
    ref = np.sort(reference[~np.isnan(reference)])
    if len(ref) == 0:
        return pd.Series(0.0, index=values.index)
    lo = np.searchsorted(ref, values.to_numpy(), side="left")
    hi = np.searchsorted(ref, values.to_numpy(), side="right")
    pct = ((lo + hi) / 2 + 0.5) / (len(ref) + 1)
    return pd.Series([_N.inv_cdf(p) for p in np.clip(pct, 1e-4, 1 - 1e-4)], index=values.index)


def qualified(m: pd.DataFrame) -> pd.Series:
    """Reference population: players with at least 15% of the season's top minute load."""
    return m.minutes >= 0.15 * m.minutes.max()


def score(m: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """Return one row per player with <attr> (1–20) and <attr>_conf (0–1) columns."""
    out = pd.DataFrame(index=m.index)
    ref_z: dict[str, pd.Series] = {}
    for a in ATTRIBUTES:
        z = sum(w * sign * _normal_scores(m[c], reference[c].to_numpy(dtype=float)) for c, w, sign in a.components)
        zr = sum(w * sign * _normal_scores(reference[c], reference[c].to_numpy(dtype=float)) for c, w, sign in a.components)
        ref_z[a.key] = zr
        sd = zr.std() or 1.0
        out[a.key] = np.clip(np.round(CENTER + SCALE * z / sd), 1, 20).astype(int)
        conf = []
        for c, _, _ in a.components:
            n = m.get(f"n_{c}", pd.Series(0, index=m.index)).astype(float)
            k = PRIOR_K.get(c, 10.0)
            conf.append(n / (n + k))
        out[f"{a.key}_conf"] = np.round(np.minimum.reduce(conf), 2)
    return out
