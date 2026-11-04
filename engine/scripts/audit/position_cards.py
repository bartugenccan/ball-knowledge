"""Do ratings match what a stat line says? One player per position, then the whole league.

    uv run python scripts/audit/position_cards.py

Read-only: writes only under data/audit/. The data list only Guard, Forward and Center, so the
five positions are picked by basketball role. Reads the built ratings, so run bk.ratings.build first.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from foundation import table  # noqa: E402
from stage3 import CARRY_GRID, K_GRID, MIN_IMPROVEMENT, first_half_games, gain, league_level  # noqa: E402

from bk.config import AUDIT_DIR, TABLES_DIR  # noqa: E402
from bk.ratings.metrics_v2 import SPECS, Spec, counts, display_value, load_tables  # noqa: E402

PLAYERS = {"PG": "CAMPAZZO, FACUNDO", "SG": "PUNTER, KEVIN", "SF": "LUWAWU-CABARROT, TIMOTHE", "PF": "VEZENKOV, SASHA", "C": "TAVARES, WALTER"}
SEASONS = ("E2025", "E2026")
REFERENCE_MINUTES = 500
SMALL_K = (2, 5, 10, 15, 20, 30)
BIG_GAP = 0.30


def usage_selection(t) -> pd.DataFrame:
    metric = "usage_rate"
    spec = SPECS[metric]
    full = counts(t.window("E2024"))[metric]
    w = t.window("E2025")
    first = first_half_games(w.player_games)
    rest = set(w.player_games.gamecode) - first
    a, b = counts(t.window("E2025", first))[metric], counts(t.window("E2025", rest))[metric]
    level = league_level(*full)

    def run(k: float, carry: float) -> float:
        return gain(Spec("rate", k, scale=100), a, b, None, [(*full, level, carry)] if carry else None)

    grid = SMALL_K + K_GRID
    by_w = {c: max(run(k, c) for k in grid) for c in CARRY_GRID}
    best = max(by_w, key=by_w.get)
    use = best if by_w[best] - by_w[0.0] >= MIN_IMPROVEMENT else 0.0
    results = {k: run(k, use) for k in grid}
    best_k = max(results, key=results.get)
    return pd.DataFrame([{"metrik": metric, "geçmişsiz": by_w[0.0], "geçmişli": by_w[best], "kurala_göre_w": use, "kurala_göre_k": best_k,
                          "kazanç": results[best_k], "koddaki": f"k={spec.k:g} w={spec.carry:g}"}])


def stat_table(t) -> pd.DataFrame:
    pg = t.player_games
    s = t.shots
    box = pg.groupby(["season", "player_id"]).agg(
        g=("gamecode", "size"), mins=("minutes", "sum"), pts=("pts", "sum"), fg2a=("fg2a", "sum"), fg3m=("fg3m", "sum"), fg3a=("fg3a", "sum"),
        ftm=("ftm", "sum"), fta=("fta", "sum"), orb=("orb", "sum"), drb=("drb", "sum"), ast=("ast", "sum"), stl=("stl", "sum"), tov=("tov", "sum"),
        blk=("blk", "sum"), pf=("pf", "sum"), fd=("fd", "sum")).reset_index()
    inside = s[s.zone_group == "inside"].groupby(["season", "player_id"]).made.agg(ins_m="sum", ins_a="size").reset_index()
    mid = s[s.zone_group == "mid"].groupby(["season", "player_id"]).made.agg(mid_m="sum", mid_a="size").reset_index()
    own = s[s.made & ~s.assisted & ~s.is_heave & (s.context != "putback")]
    creation = own.groupby(["season", "player_id"]).value.sum().rename("self_pts").reset_index()
    d = box.merge(inside, how="left").merge(mid, how="left").merge(creation, how="left").fillna(0)
    d["touch"] = d.fg2a + d.fg3a + 0.44 * d.fta + d.tov + d.ast
    return d


def raw_values(d: pd.DataFrame) -> dict[str, pd.Series]:
    """A plain number per attribute, higher is better, for comparing with the rating."""
    return {
        "finishing": 2 * d.ins_m / d.g, "three_point": d.fg3m / d.g, "mid_range": d.mid_m / d.g, "free_throw": d.ftm / d.fta.replace(0, np.nan),
        "shot_creation": d.self_pts / d.g, "passing": d.ast / d.g, "ball_security": d.touch / d.tov.replace(0, np.nan), "drawing_fouls": d.fd / d.g,
        "off_rebounding": d.orb / d.g, "def_rebounding": d.drb / d.g, "steals": d.stl / d.g, "shot_blocking": d.blk / d.g, "discipline": -d.pf / d.g,
        "stamina": d.mins / d.g,
    }


def card(x: pd.Series, met: pd.Series) -> dict[str, str]:
    g = x.g

    def shots(m: float, a: float) -> str:
        return f"{m / g:.1f}/{a / g:.1f}, %{100 * m / max(a, 1):.0f}"

    on_off = "-" if pd.isna(met.opp_inside_pct_on) else (f"rakip boyalı %{100 * met.opp_inside_pct_on:.0f} (kenarda %{100 * met.opp_inside_pct_off:.0f}), "
                                                         f"{met.opp_inside_fga_on:.0f} deneme ({met.opp_inside_fga_off:.0f})")
    return {
        "finishing": shots(x.ins_m, x.ins_a), "mid_range": shots(x.mid_m, x.mid_a), "three_point": shots(x.fg3m, x.fg3a), "free_throw": shots(x.ftm, x.fta),
        "shot_creation": f"{x.self_pts / g:.1f} asistsiz sayı", "passing": f"{x.ast / g:.1f} asist", "ball_security": f"{x.tov / g:.1f} kayıp, {x.touch / g:.0f} temas",
        "drawing_fouls": f"{x.fd / g:.1f} faul", "off_rebounding": f"{x.orb / g:.1f}", "def_rebounding": f"{x.drb / g:.1f}", "steals": f"{x.stl / g:.1f}",
        "shot_blocking": f"{x.blk / g:.1f}", "rim_protection": f"{x.blk / g:.1f} blok; {on_off}", "perimeter_defense": f"{x.stl / g:.1f} top çalma",
        "discipline": f"{x.pf / g:.1f} faul", "team_defense": "saha içi etki", "stamina": f"{x.mins / g:.1f} dk", "consistency": f"{int(g)} maç",
    }


def main() -> None:
    t = load_tables()
    ratings = pd.read_parquet(TABLES_DIR / "ratings_season.parquet")
    metrics = pd.read_parquet(TABLES_DIR / "player_metrics.parquet")
    stats = stat_table(t)
    joined = ratings.merge(stats, on=["season", "player_id"])
    keys = [c[:-5] for c in ratings.columns if c.endswith("_conf")]
    from bk.ratings.catalog import ATTR_BY_KEY

    out = ["# Mevki kartları\n", "Her hücre: ham istatistik ve gösterilen puan. Yüzdelik, en az 500 dakika oynayan oyuncular arasında ham istatistiğin sırası.\n",
           "## Top kullanımı parametresi\n", table(usage_selection(t)), ""]
    for season in SEASONS:
        reference = joined[(joined.season == season) & (joined.minutes >= REFERENCE_MINUTES)] if season != "E2026" else joined[(joined.season == season) & joined.qualified]
        raw = raw_values(reference)
        out.append(f"## {season}\n")
        rows = {k: {"özellik": ATTR_BY_KEY[k].label} for k in keys}
        meta = {}
        for pos, name in PLAYERS.items():
            x = joined[(joined.season == season) & (joined.player == name)]
            if x.empty:
                continue
            x = x.iloc[0]
            met = metrics[(metrics.season == season) & (metrics.player_id == x.player_id)].iloc[0]
            cells = card(x, met)
            meta[pos] = f"{name.title()} ({x.team}, {x.pts / x.g:.1f} sayı, {x.mins / x.g:.1f} dk)"
            for k in keys:
                shown = display_value(k, int(x[k]), bool(x.three_non_shooter), int(x.games), bool(x.mid_non_shooter))
                pct = ""
                if k in raw:
                    value = raw_values(joined[(joined.season == season) & (joined.player == name)])[k].iloc[0]
                    if pd.notna(value):
                        pct = f", {100 * (raw[k].dropna() < value).mean():.0f}. yüzdelik"
                rows[k][pos] = f"{cells[k]}{pct} → **{shown}**"
        out += ["; ".join(f"{p}: {v}" for p, v in meta.items()) + "\n", table(pd.DataFrame(list(rows.values()))), ""]

    f = joined[(joined.season == "E2025") & (joined.minutes >= REFERENCE_MINUTES)].reset_index(drop=True)
    raw = raw_values(f)
    rows = []
    for k, value in raw.items():
        shown = pd.notna(value)
        gap = (f[k][shown].rank(pct=True) - value[shown].rank(pct=True))
        worst = gap.abs().sort_values(ascending=False).index[:5]
        rows.append({"özellik": ATTR_BY_KEY[k].label, "puan_stat_r": f[k][shown].corr(value[shown]), "büyük_sapma": int((gap.abs() > BIG_GAP).sum()),
                     "en_çok_sapanlar": ", ".join(f"{f.player[i].split(',')[0].title()} {int(f[k][i])} ({'yüksek' if gap[i] > 0 else 'düşük'})" for i in worst)})
    out += ["## Ligin tamamı: puan ve ham istatistik (E2025, 500+ dk)\n",
            f"`büyük_sapma`: puan sırası ile istatistik sırası %{100 * BIG_GAP:.0f}'den fazla farklı olan oyuncu sayısı. Sapma tek başına hata değil: puan küçültme, geçmiş sezon ve maç başına değil hücum başına hesaplama da içeriyor.\n",
            table(pd.DataFrame(rows).sort_values("puan_stat_r")), ""]
    text = "\n".join(out)
    (AUDIT_DIR / "position_cards.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
