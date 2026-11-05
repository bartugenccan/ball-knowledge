"""How often does each kind of pre-game claim come true? This sets how boldly the preview may speak.

    uv run python scripts/match/claim_card.py [--likely]

Reads the scorecard, simulates nothing. A claim is what the simulated averages say before the game; it
comes true if the real game agrees. Winning the factor is shown too: an edge that came true but did not
help win games is not worth much of a sentence.

Writes data/audit/match_claim_card.md.
"""

from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from bk.config import AUDIT_DIR  # noqa: E402

STRONG, FAIR = 0.65, 0.57   # came true this often: say it plainly, say it with care, or leave it out


def side_claim(g: pd.DataFrame, stat: str, levels: tuple[float, ...], label: str, lower_better: bool = False) -> list[list]:
    """The side with the higher simulated number also has the higher real one?"""
    sim = g[f"h_{stat}_sim"] - g[f"a_{stat}_sim"]
    real = g[f"h_{stat}_real"] - g[f"a_{stat}_real"]
    won = g.h_pts_real > g.a_pts_real
    rows = []
    for level in levels:
        m = (sim.abs() >= level) & (real != 0)
        if m.sum() < 20:
            continue
        came_true = float((np.sign(sim[m]) == np.sign(real[m])).mean())
        # did having the real edge go with winning?
        better_real = real[real != 0] > 0 if not lower_better else real[real != 0] < 0
        helped = float((better_real == won[real != 0]).mean())
        rows.append([label, f"fark ≥ {level:g}", int(m.sum()), f"{came_true:.0%}", f"{helped:.0%}", _tone(came_true)])
    return rows


def _tone(rate: float) -> str:
    return "net söylenir" if rate >= STRONG else "temkinli söylenir" if rate >= FAIR else "yazılmaz"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--likely", action="store_true")
    a = ap.parse_args()
    tag = "_likely" if a.likely else ""
    g = pd.read_parquet(AUDIT_DIR / f"match_scorecard{tag}_enriched.parquet")
    for name in ("h", "a"):
        g[f"{name}_efg_sim"] = 100 * (g[f"{name}_f2m_sim"] + 1.5 * g[f"{name}_f3m_sim"]) / g[f"{name}_fga_sim"]
        g[f"{name}_efg_real"] = 100 * (g[f"{name}_f2m_real"] + 1.5 * g[f"{name}_f3m_real"]) / g[f"{name}_fga_real"]

    rows: list[list] = []
    rows += side_claim(g, "orb", (0.5, 1, 1.5, 2), "Hücum ribaundu daha çok")
    rows += side_claim(g, "drb", (1, 2, 3), "Savunma ribaundu daha çok")
    rows += side_claim(g, "tov", (0.5, 1, 1.5), "Top kaybı daha çok", lower_better=True)
    rows += side_claim(g, "ftm", (1, 2, 3), "Çizgiden daha çok sayı")
    rows += side_claim(g, "f3a", (2, 4, 6), "Daha çok üçlük")
    rows += side_claim(g, "inside_a", (2, 4, 6), "Boyalıya daha çok giriş")
    rows += side_claim(g, "ast", (1, 2, 3), "Daha çok asist")
    rows += side_claim(g, "stl", (0.5, 1), "Daha çok top çalma")
    rows += side_claim(g, "blk", (0.5, 1), "Daha çok blok")
    rows += side_claim(g, "efg", (1, 2, 3, 4), "Daha yüksek şut verimi")
    rows += side_claim(g, "pts", (2, 4, 6, 8), "Kazanan")

    lines = ["# İddia karnesi", "", f"{len(g)} maç. Maç önü bir iddia, gerçekte ne sıklıkla tuttu? Son sütun, metinde nasıl yer alacağı: en az %{100 * STRONG:.0f} net, en az %{100 * FAIR:.0f} temkinli, altı yazılmaz. \"Maça etkisi\": gerçekte bu üstünlüğü alan takımın maçı kazanma oranı.", "",
             "| İddia | Eşik | Maç | Tuttu | Maça etkisi | Metinde |", "|---|---|---:|---:|---:|---|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]

    # kinds of game, against how often it happens anyway
    sim_margin = (g.h_pts_sim - g.a_pts_sim).abs()
    real_margin = (g.h_pts_real - g.a_pts_real).abs()
    total_sim, total_real = g.h_pts_sim + g.a_pts_sim, g.h_pts_real + g.a_pts_real
    poss_sim, poss_real = g.h_poss_sim + g.a_poss_sim, g.h_poss_real + g.a_poss_real
    lines += ["", "## Maçın karakteri", "", "| İddia | Maç | Tuttu | Zaten olma oranı |", "|---|---:|---:|---:|"]
    kinds = [("Başa baş (beklenen fark ≤ 2): gerçek fark ≤ 8", sim_margin <= 2, real_margin <= 8), ("Açık fark (beklenen ≥ 8): gerçek fark ≥ 10", sim_margin >= 8, real_margin >= 10),
             ("Yüksek skor (beklenen toplam ≥ 178): gerçek ≥ 172", total_sim >= 178, total_real >= 172), ("Düşük skor (beklenen toplam ≤ 166): gerçek < 172", total_sim <= 166, total_real < 172),
             ("Hızlı (beklenen hücum ≥ 150): gerçek ≥ 147", poss_sim >= 150, poss_real >= 147), ("Yavaş (beklenen hücum ≤ 144): gerçek < 147", poss_sim <= 144, poss_real < 147),
             ("Çekişmeli (beklenen top değişimi ≥ 8): gerçek ≥ 6", g.lead_changes_sim >= 8, g.lead_changes_real >= 6)]
    for text, cond, outcome in kinds:
        if cond.sum() >= 15:
            lines.append(f"| {text} | {int(cond.sum())} | {outcome[cond].mean():.0%} | {outcome.mean():.0%} |")
    out = "\n".join(lines) + "\n"
    (AUDIT_DIR / f"match_claim_card{tag}.md").write_text(out, encoding="utf-8")
    print(out.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
