"""Try each model change on its own, on all 492 games, against the same games without it.

    uv run python scripts/match/candidates.py [--sims 400] [--only name ...]

Run scripts/match/scorecard.py --rebuild first, since the prepared teams come from its cache.
The rule is fixed here, before the results:

    KEPT if its main measure improves by at least one paired standard error over all games, moves
    the right way in both E2025 and E2026, and no other main measure gets worse by more than one
    paired standard error.

Each run is added to data/audit/match_candidates.md as soon as it finishes.
"""

from __future__ import annotations

import argparse
import pickle
import warnings
from concurrent.futures import ProcessPoolExecutor

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scorecard import CACHE, _simulate  # noqa: E402

from bk.config import AUDIT_DIR  # noqa: E402
from bk.match.model import load_league  # noqa: E402
from bk.match.sim import Tuning  # noqa: E402

LEDGER = AUDIT_DIR / "match_candidates.md"
SEASONS = ("E2025", "E2026")
GUARDED = ("log_loss", "margin", "points", "minutes")

# name, settings, main measure
CANDIDATES: list[tuple[str, dict, str]] = [
    ("Pivot sınırı kalkıyor (iki pivot serbest)", {"max_centers": 2.0}, "minutes"),
    ("Takım gücü %25", {"team_strength": 0.25}, "log_loss"),
    ("Takım gücü %50", {"team_strength": 0.50}, "log_loss"),
    ("Takım gücü %75", {"team_strength": 0.75}, "log_loss"),
    ("Takım gücü %100", {"team_strength": 1.00}, "log_loss"),
    ("Yıldız: şut payı üssü 1,1", {"usage_power": 1.1}, "points"),
    ("Yıldız: şut payı üssü 1,2", {"usage_power": 1.2}, "points"),
    ("Hacim: şut +%3, üçlük isabeti -0,055", {"shot_scale": 1.03, "three_make_shift": -0.055}, "attempts"),
    ("Dakika: son 3 maç %50", {"recent_minutes": 0.5}, "minutes"),
    # kept one by one above; they may not add up
    ("Birleşim: dördü birden", {"max_centers": 2.0, "team_strength": 0.25, "usage_power": 1.2, "recent_minutes": 0.5}, "log_loss"),
    ("Birleşim: takım gücü olmadan", {"max_centers": 2.0, "usage_power": 1.2, "recent_minutes": 0.5}, "log_loss"),
    # second round, from the story card: teams look too much alike, and closers are no better than a season average.
    # Starting point: the settings kept above. Each value below was set before seeing its result.
    ("Tur 2: tempo ve geçiş farkı iki katı", {"tempo_scale": 2.0, "transition_scale": 2.0}, "style"),
    ("Tur 2: takımın kendi top kaybı eğilimi", {"own_to_scale": 1.0}, "style"),
    ("Tur 2: takımın çizgiye gitme eğilimi", {"own_foul_scale": 1.0}, "style"),
    ("Tur 2: takımın ribaund eğilimi", {"orb_team_scale": 1.0}, "style"),
    ("Tur 2: orta mesafe ve geçiş düzeyi", {"mid_scale": 1.14, "transition_shift": 0.17}, "style"),
    ("Tur 2: maçı bitirenler", {"closer_weight": 1.0}, "closers"),
    # third round: these missed the style measure above but moved the score, so they are a new hypothesis with the
    # score as main measure. Same games as before, so read the result as optimistic until new rounds confirm it.
    ("Tur 3: takım ribaund eğilimi %50", {"orb_team_scale": 0.5}, "margin"),
    ("Tur 3: takım ribaund eğilimi %100", {"orb_team_scale": 1.0}, "margin"),
    ("Tur 3: tempo ve geçiş iki katı", {"tempo_scale": 2.0, "transition_scale": 2.0}, "margin"),
    ("Tur 3: ribaund %100 ve tempo iki katı", {"orb_team_scale": 1.0, "tempo_scale": 2.0, "transition_scale": 2.0}, "margin"),
]
MEASURES = {"log_loss": "Kazanan log-kaybı", "margin": "Skor farkı kare hata", "points": "Oyuncu sayı hatası", "minutes": "Oyuncu dakika hatası", "attempts": "Takım şut denemesi hatası",
            "style": "Takım oyun stili hatası", "closers": "Son 5 dakika oyuncu hatası"}
STYLE_STATS = ("poss", "f3a", "inside_a", "mid_a", "fta", "tov", "orb")
STYLE_UNITS = {"poss": 6.6, "f3a": 7.6, "inside_a": 8.9, "mid_a": 4.5, "fta": 10.3, "tov": 5.2, "orb": 5.2}  # two teams' usual error per game, fixed so runs stay comparable


def run(games: list[dict], league: dict, tune: Tuning, sims: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    with ProcessPoolExecutor(8) as pool:
        results = list(pool.map(_simulate, [(g, league, sims, tune) for g in games], chunksize=4))
    return pd.DataFrame([r for r, _ in results]), pd.DataFrame([p for _, ps in results for p in ps])


def measures(g: pd.DataFrame, pl: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """One row per unit for each measure, lower is better, so two runs can be compared pair by pair."""
    y = (g.h_pts_real > g.a_pts_real).astype(float)
    p = g.p_home.clip(0.01, 0.99)
    game = pd.DataFrame({"season": g.season, "gamecode": g.gamecode})
    out = {"log_loss": game.assign(v=-(y * np.log(p) + (1 - y) * np.log(1 - p))),
           "margin": game.assign(v=((g.h_pts_real - g.a_pts_real) - (g.h_pts_sim - g.a_pts_sim)) ** 2),
           "attempts": game.assign(v=(g.h_fga_real - g.h_fga_sim).abs() + (g.a_fga_real - g.a_fga_sim).abs())}
    # each team stat in units of its own typical error, so one stat does not outweigh the rest
    style = 0.0
    for k in STYLE_STATS:
        gap = (g[f"h_{k}_real"] - g[f"h_{k}_sim"]).abs() + (g[f"a_{k}_real"] - g[f"a_{k}_sim"]).abs()
        style = style + gap / STYLE_UNITS[k]
    out["style"] = game.assign(v=style / len(STYLE_STATS))
    player = pd.DataFrame({"season": pl.season, "gamecode": pl.gamecode, "player_id": pl.player_id})
    out["closers"] = player.assign(v=(pl.late_real - pl.late_sim).abs() / 60)
    out["points"] = player.assign(v=(pl.pts_real - pl.pts_sim).abs())
    out["minutes"] = player.assign(v=(pl.sec_real - pl.sec_sim).abs() / 60)
    return out


def compare(base: dict[str, pd.DataFrame], new: dict[str, pd.DataFrame]) -> dict[str, dict]:
    """New minus base. Negative is better. Standard errors treat a game as the independent unit."""
    out = {}
    for key in base:
        keys = ["season", "gamecode"] + (["player_id"] if "player_id" in base[key] else [])
        d = base[key].merge(new[key], on=keys, suffixes=("_b", "_n"))
        d["d"] = d.v_n - d.v_b
        per_game = d.groupby(["season", "gamecode"]).d.mean().reset_index()
        row = {"all": float(per_game.d.mean()), "se": float(per_game.d.std(ddof=1) / np.sqrt(len(per_game))), "base": float(d.v_b.mean()), "new": float(d.v_n.mean())}
        for s in SEASONS:
            row[s] = float(per_game[per_game.season == s].d.mean())
        out[key] = row
    return out


def decide(result: dict[str, dict], main: str) -> tuple[bool, str]:
    m = result[main]
    if m["all"] > -m["se"]:
        return False, "ana ölçütte bir standart hatayı aşan iyileşme yok"
    if m["E2025"] >= 0 or m["E2026"] >= 0:
        return False, "iki sezonda aynı yönde değil"
    hurt = [MEASURES[k] for k, v in result.items() if k in GUARDED and v["all"] > v["se"]]
    if hurt:
        return False, "şunu bozuyor: " + ", ".join(hurt)
    return True, "kuralı geçti"


def bias_rows(g: pd.DataFrame, pl: pd.DataFrame) -> str:
    high = pl[pl.usage >= 26]
    low = pl[pl.usage < 14]
    center = pl[pl.position == "Center"]
    f3 = (g.h_f3m_sim.sum() + g.a_f3m_sim.sum()) / (g.h_f3a_sim.sum() + g.a_f3a_sim.sum())
    f3r = (g.h_f3m_real.sum() + g.a_f3m_real.sum()) / (g.h_f3a_real.sum() + g.a_f3a_real.sum())
    return (f"Sapmalar: pivot dakikası {(center.sec_sim - center.sec_real).mean() / 60:+.2f}, çok yüksek kullanım sayısı {(high.pts_sim - high.pts_real).mean():+.2f}, düşük kullanım sayısı {(low.pts_sim - low.pts_real).mean():+.2f}, "
            f"takım şut denemesi {((g.h_fga_sim - g.h_fga_real).mean() + (g.a_fga_sim - g.a_fga_real).mean()) / 2:+.2f}, üçlük yüzdesi {100 * (f3 - f3r):+.2f}, takım sayısı {((g.h_pts_sim - g.h_pts_real).mean() + (g.a_pts_sim - g.a_pts_real).mean()) / 2:+.2f}, "
            f"skor farkı %80 {g.margin_in_80.mean():.0%}, toplam %80 {g.total_in_80.mean():.0%}.")


def write_entry(name: str, settings: dict, main: str, result: dict[str, dict], kept: bool, why: str, notes: str) -> None:
    lines = [f"## {name}", "", f"Ayar: `{settings}`. Ana ölçüt: {MEASURES[main]}. **{'TUTULDU' if kept else 'ELENDİ'}**: {why}.", "",
             "| Ölçüt | Önce | Sonra | Fark | SE | E2025 | E2026 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for k, v in result.items():
        lines.append(f"| {MEASURES[k]} | {v['base']:.4f} | {v['new']:.4f} | {v['all']:+.4f} | {v['se']:.4f} | {v['E2025']:+.4f} | {v['E2026']:+.4f} |")
    lines += ["", notes, "", ""]
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=400)
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()
    games = pickle.loads(CACHE.read_bytes())
    league = load_league()
    base_g, base_p = run(games, league, Tuning(), a.sims)
    base = measures(base_g, base_p)
    if a.only is None:
        LEDGER.write_text("# Model adayları\n\nKural, sonuçlardan önce yazıldı: ana ölçüt tüm maçlarda en az bir eşli standart hata iyileşmeli, E2025 ve E2026'da aynı yönde olmalı, diğer ana ölçütler bir standart hatadan fazla bozulmamalı. Farklar sonra eksi önce: eksi iyi.\n\n"
                          + "Başlangıç. " + bias_rows(base_g, base_p) + "\n\n", encoding="utf-8")
    for name, settings, main_measure in CANDIDATES:
        if a.only and not any(o in name for o in a.only):
            continue
        g, p = run(games, league, Tuning(**settings), a.sims)
        result = compare(base, measures(g, p))
        kept, why = decide(result, main_measure)
        write_entry(name, settings, main_measure, result, kept, why, bias_rows(g, p))
        print(name, "KEPT" if kept else "dropped", why, {k: round(v["all"], 4) for k, v in result.items()}, flush=True)


if __name__ == "__main__":
    main()
