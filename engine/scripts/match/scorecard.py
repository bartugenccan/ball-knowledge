"""Every game of E2025 and E2026, simulated from before it was played, against what happened.

    uv run python scripts/match/scorecard.py [--rebuild] [--sims 400]

Writes one row per game and one per player-game to data/audit/match_scorecard_*.parquet, so any later
question can be answered without simulating again, and a report to data/audit/match_scorecard.md.
Changes nothing in the model.
"""

from __future__ import annotations

import argparse
import pickle
import warnings
from concurrent.futures import ProcessPoolExecutor

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from bk.config import AUDIT_DIR, DATA_DIR  # noqa: E402
from bk.match.baselines import NetRatings, net_rating_probabilities, player_averages  # noqa: E402
from bk.match.evaluate import clip, inside_80  # noqa: E402
from bk.match.model import actual_roster, build_team, likely_roster, load_league, snapshot  # noqa: E402
from bk.match.runner import actual_game, games_table, run_many  # noqa: E402
from bk.ratings.metrics_v2 import load_tables  # noqa: E402

SEASONS = ("E2025", "E2026")
CACHE = DATA_DIR / "match_cache" / "scorecard_games.pkl"
LIKELY_CACHE = DATA_DIR / "match_cache" / "scorecard_likely_games.pkl"
MIN_LIKELY_SQUAD = 8
TEAM_STATS = ("pts", "poss", "fga", "f2a", "f2m", "f3a", "f3m", "fta", "ftm", "orb", "drb", "ast", "stl", "blk", "tov", "pf", "inside_a", "inside_m", "mid_a", "mid_m")
PLAYER_STATS = {"sec": "minutes", "pts": "pts", "f2a": "fg2a", "f3a": "fg3a", "fta": "fta", "orb": "orb", "drb": "drb", "ast": "ast", "tov": "tov", "pf": "pf", "stl": "stl", "blk": "blk"}


def moments_of(season_games: pd.DataFrame) -> list[tuple[object, pd.DataFrame]]:
    """Groups that share one view of the past: a regular-season round, or a single date after it.

    Play-off series run over days inside one round, and game two should know about game one.
    """
    regular = season_games[season_games.phase == "RS"]
    rest = season_games[season_games.phase != "RS"]
    groups = [(g.date.min(), g) for _, g in regular.groupby("round")]
    groups += [(g.date.min(), g) for _, g in rest.groupby(rest.date.dt.date)]
    return sorted(groups, key=lambda x: x[0])


def prepare(t, likely: bool = False) -> list[dict]:
    """likely: the squad and starters as they could be guessed before the game, not the real ones."""
    g = games_table()
    out = []
    for season in SEASONS:
        part = g[g.season == season].sort_values("date")
        for when, games in moments_of(part):
            snap = snapshot(t, season, when)
            for r in games.itertuples():
                rosters = {}
                for code in (r.home, r.away):
                    real = actual_roster(t.player_games, season, r.gamecode, code)
                    rosters[code] = likely_roster(snap, code) if likely else real
                # the first game of a team's season has nothing to guess from
                if min(len(rosters[r.home]), len(rosters[r.away])) < MIN_LIKELY_SQUAD:
                    continue
                entry = {"season": season, "gamecode": int(r.gamecode), "home": build_team(snap, r.home, rosters[r.home]),
                         "away": build_team(snap, r.away, rosters[r.away]), "actual": actual_game(t, season, r.gamecode, r.home, r.away)}
                if likely:
                    entry["real_rosters"] = {code: actual_roster(t.player_games, season, r.gamecode, code) for code in (r.home, r.away)}
                out.append(entry)
            print(season, str(when)[:10], len(games), "games ready", flush=True)
    path = LIKELY_CACHE if likely else CACHE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(out))
    return out


def _simulate(args) -> tuple[dict, list[dict]]:
    game, league, sims, *tune = args
    m = run_many(game["home"], game["away"], league, tune[0] if tune else None, sims, seed=game["gamecode"] * 1000 + int(game["season"][1:]))
    actual = game["actual"]
    margin = m.home_pts - m.away_pts
    total = m.home_pts + m.away_pts
    h, a = actual["team"][0]["pts"], actual["team"][1]["pts"]
    row: dict = {"season": game["season"], "gamecode": game["gamecode"], "home": m.home.code, "away": m.away.code,
                 "p_home": clip(m.home_win, m.n), "margin_sd": float(margin.std()), "total_sd": float(total.std()),
                 "margin_in_80": inside_80(margin, h - a), "total_in_80": inside_80(total, h + a),
                 "lead_changes_sim": float(m.flow["lead_changes"].mean()), "lead_changes_real": actual["flow"]["lead_changes"],
                 "best_run_sim": float((m.flow["best_run_home"] + m.flow["best_run_away"]).mean() / 2),
                 "best_run_real": (actual["flow"]["best_run_home"] + actual["flow"]["best_run_away"]) / 2,
                 "max_lead_sim": float((m.flow["max_lead_home"] + m.flow["max_lead_away"]).mean() / 2),
                 "max_lead_real": (actual["flow"]["max_lead_home"] + actual["flow"]["max_lead_away"]) / 2,
                 "subs_sim": float(m.subs.mean()), "subs_real": float(np.mean(actual["subs"])), "overtime_real": actual["overtime"]}
    for side, name in ((0, "h"), (1, "a")):
        for k in TEAM_STATS:
            row[f"{name}_{k}_sim"] = float(m.team[side][k].mean())
            row[f"{name}_{k}_real"] = float(actual["team"][side][k])
            row[f"{name}_{k}_in80"] = inside_80(m.team[side][k], actual["team"][side][k])
    if "real_rosters" in game:
        named = starters = 0
        lost = 0.0
        for team in (m.home, m.away):
            real = game["real_rosters"][team.code]
            ours = {p.player_id for p in team.players}
            our_five = {p.player_id for p in team.players if p.starter}
            starters += len(our_five & {pid for pid, _, is_starter in real if is_starter})
            named += len({pid for pid, _, _ in real} & ours)
            lost += sum(actual["players"][pid]["sec"] for pid, _, _ in real if pid not in ours and pid in actual["players"]) / 60
        row["starters_right"], row["squad_named"], row["real_minutes_missing"] = starters / 10, named, lost
    players = []
    cols = m.box_columns
    for side, team in ((0, m.home), (1, m.away)):
        for j, p in enumerate(team.players):
            real = actual["players"].get(p.player_id)
            if real is None:
                continue
            rec = {"season": game["season"], "gamecode": game["gamecode"], "team": team.code, "side": side, "player_id": p.player_id, "player": p.name,
                   "position": p.position, "starter": p.starter, "target": p.target, "games_before": p.games_before,
                   "usage": p.rate["inside"] + p.rate["mid"] + p.rate["three"] + p.tov, "known": bool(p.ratings)}
            for k in PLAYER_STATS:
                v = m.players[side][:, j, cols.index(k)]
                rec[f"{k}_sim"] = float(v.mean())
                rec[f"{k}_real"] = float(real[k])
                rec[f"{k}_in80"] = inside_80(v, real[k])
            rec["late_sim"] = float(m.player_parts[side][:, j, 4].mean())
            rec["late_real"] = float(real["late"])
            players.append(rec)
    return row, players


def gap_points(g: pd.DataFrame) -> pd.DataFrame:
    """For each team-game: where the points gap to the simulation came from, split into volume and accuracy."""
    frames = []
    for name in ("h", "a"):
        x = pd.DataFrame(index=g.index)
        p2 = g[f"{name}_f2m_sim"] / g[f"{name}_f2a_sim"].clip(lower=1)
        p3 = g[f"{name}_f3m_sim"] / g[f"{name}_f3a_sim"].clip(lower=1)
        a2, a3 = g[f"{name}_f2a_real"], g[f"{name}_f3a_real"]
        x["two_accuracy"] = 2 * (g[f"{name}_f2m_real"] - a2 * p2)
        x["three_accuracy"] = 3 * (g[f"{name}_f3m_real"] - a3 * p3)
        x["two_volume"] = 2 * (a2 - g[f"{name}_f2a_sim"]) * p2
        x["three_volume"] = 3 * (a3 - g[f"{name}_f3a_sim"]) * p3
        x["free_throws"] = g[f"{name}_ftm_real"] - g[f"{name}_ftm_sim"]
        x["total"] = g[f"{name}_pts_real"] - g[f"{name}_pts_sim"]
        # how much the accuracy gap would vary from chance alone, given the shots taken
        x["two_chance_var"] = (2 ** 2) * a2 * p2 * (1 - p2)
        x["three_chance_var"] = (3 ** 2) * a3 * p3 * (1 - p3)
        x["team"] = g["home"] if name == "h" else g["away"]
        x["is_home"] = name == "h"
        x["season"], x["gamecode"] = g.season, g.gamecode
        frames.append(x)
    return pd.concat(frames, ignore_index=True)


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 0.01, 0.99)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def paired(y: np.ndarray, p: np.ndarray, q: np.ndarray) -> tuple[float, float]:
    """Log-loss of p minus log-loss of q, with its standard error."""
    p, q = np.clip(p, 0.01, 0.99), np.clip(q, 0.01, 0.99)
    d = -(y * np.log(p) + (1 - y) * np.log(1 - p)) + (y * np.log(q) + (1 - y) * np.log(1 - q))
    return float(d.mean()), float(d.std(ddof=1) / np.sqrt(len(d)))


def table(rows: list[list], header: list[str]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---:|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def report(g: pd.DataFrame, pl: pd.DataFrame) -> str:
    y = g.home_won.to_numpy(dtype=float)
    lines = ["# Tüm maçların karnesi", "", f"{len(g)} maç, {len(pl)} oyuncu-maç. Her biri yalnızca kendinden önceki veriyle oynatıldı. Ayarlar E2025'te seçilmişti.", ""]

    def winners(mask, label):
        y_, p_, n_ = y[mask], g.p_home[mask].to_numpy(), g.p_net[mask].to_numpy()
        ok = ~np.isnan(n_)
        margin = (g.h_pts_real - g.a_pts_real)[mask]
        sim = (g.h_pts_sim - g.a_pts_sim)[mask]
        total = (g.h_pts_real + g.a_pts_real)[mask]
        tsim = (g.h_pts_sim + g.a_pts_sim)[mask]
        d, se = paired(y_[ok], p_[ok], n_[ok]) if ok.sum() > 1 else (float("nan"), float("nan"))
        return [label, int(mask.sum()), f"{log_loss(y_, p_):.3f}", f"{log_loss(y_[ok], n_[ok]):.3f}" if ok.any() else "-", f"{d:+.3f} ({se:.3f})",
                f"{np.mean((p_ > .5) == (y_ == 1)):.0%}", f"{(margin - sim).abs().mean():.1f}", f"{(margin - sim).mean():+.1f}", f"{(total - tsim).mean():+.1f}",
                f"{g.margin_in_80[mask].mean():.0%}", f"{g.total_in_80[mask].mean():.0%}"]

    header = ["Kesit", "Maç", "Log-kayıp", "Net reyting", "Fark (SE)", "Kazanan", "Fark hatası", "Fark sapması", "Toplam sapması", "Fark %80", "Toplam %80"]
    rows = [winners(np.ones(len(g), dtype=bool), "Hepsi")]
    for s in SEASONS:
        rows.append(winners((g.season == s).to_numpy(), s))
    rows.append(winners(((g.season == "E2025") & (g.phase == "RS")).to_numpy(), "E2025 normal sezon"))
    rows.append(winners(((g.season == "E2025") & (g.phase != "RS")).to_numpy(), "E2025 play-in, play-off, final four"))
    early = (g.phase == "RS") & (g["round"] <= 5)
    rows.append(winners(early.to_numpy(), "İlk 5 hafta"))
    rows.append(winners(((g.phase == "RS") & g["round"].between(6, 15)).to_numpy(), "6-15. hafta"))
    rows.append(winners(((g.phase == "RS") & (g["round"] >= 16)).to_numpy(), "16. hafta sonrası"))
    for label, mask in (("Ev sahibi az dinlenmiş (fark ≤ -2 gün)", g.rest_gap <= -2), ("Dinlenme eşit (±1)", g.rest_gap.abs() <= 1), ("Ev sahibi çok dinlenmiş (fark ≥ 2)", g.rest_gap >= 2)):
        rows.append(winners(mask.to_numpy(), label))
    lines += ["## Kazanan ve skor", "", "Fark, simülasyon log-kaybından net reyting log-kaybı çıkarılarak hesaplandı: eksi simülasyon lehine. Net reyting yalnızca bitmiş sezonlarla kuruldu, bu yüzden en az bir önceki sezon gerekir.", ""]
    lines += table(rows, header)

    # how much is left to explain
    err = (g.h_pts_real - g.a_pts_real) - (g.h_pts_sim - g.a_pts_sim)
    rmse = float(np.sqrt((err ** 2).mean()))
    within = float(np.sqrt((g.margin_sd ** 2).mean()))
    room = float(np.sqrt(max(rmse ** 2 - within ** 2, 0)))
    lines += ["", "## Ne kadarı azaltılabilir?", "",
              f"Skor farkı hatası (RMSE) {rmse:.1f}. Simülasyonun aynı eşleşmede kendi ürettiği dağılım {within:.1f}. Aradaki pay en fazla {room:.1f} sayı: modelin önceden bilip bilemeyeceği kısım bu kadar, gerisi hücum hücum şans (simülasyonun şansı doğru ölçtüğü varsayımıyla).", ""]

    # are the model's team differences too small, and does net rating know something it does not?
    rows = []
    sim_margin = g.h_pts_sim - g.a_pts_sim
    real_margin = g.h_pts_real - g.a_pts_real
    for label, mask in (("Hepsi", np.ones(len(g), dtype=bool)), *((s, (g.season == s).to_numpy()) for s in SEASONS)):
        x, r = sim_margin[mask].to_numpy(), real_margin[mask].to_numpy()
        slope = float(np.polyfit(x, r, 1)[0])
        n = g.net_gap[mask].to_numpy()
        design = np.column_stack([np.ones(len(x)), x, n])
        beta, *_ = np.linalg.lstsq(design, r, rcond=None)
        resid = r - design @ beta
        cov = np.linalg.inv(design.T @ design) * resid.var(ddof=3)
        rows.append([label, f"{x.std():.1f}", f"{slope:.2f}", f"{np.corrcoef(x, r)[0, 1]:.3f}", f"{np.corrcoef(n, r)[0, 1]:.3f}", f"{beta[1]:.2f} ({np.sqrt(cov[1, 1]):.2f})", f"{beta[2]:.2f} ({np.sqrt(cov[2, 2]):.2f})"])
    lines += ["## Takım gücü sıkışık mı?", "", "Eğim: gerçek fark, simülasyonun beklediği farka göre ne kadar değişiyor. 1'in üzeri, modelin takım farklarını küçük gördüğü anlamına gelir. Son iki sütun, simülasyon ve net reyting birlikte kullanılınca her birinin katsayısı: net reytingin katsayısı sıfırdan belirgin büyükse, simülasyonun kaçırdığı bir bilgi vardır.", ""]
    lines += table(rows, ["Kesit", "Beklenen fark SD", "Eğim", "Korelasyon", "Net reyting korelasyonu", "Simülasyon katsayısı (SE)", "Net reyting katsayısı (SE)"])
    lines += [""]

    gaps = gap_points(g)
    rows = []
    for col, label, chance in (("three_accuracy", "Üçlük isabeti", "three_chance_var"), ("two_accuracy", "İki sayılık isabeti", "two_chance_var"), ("three_volume", "Üçlük hacmi", None),
                               ("two_volume", "İki sayılık hacmi", None), ("free_throws", "Serbest atış", None)):
        var = float(gaps[col].var())
        share = var / float(gaps.total.var())
        if chance:
            expect = float(gaps[chance].mean())
            rows.append([label, f"{gaps[col].mean():+.2f}", f"{np.sqrt(var):.1f}", f"{share:.0%}", f"{np.sqrt(expect):.1f}", f"{max(var - expect, 0) / var:.0%}"])
        else:
            rows.append([label, f"{gaps[col].mean():+.2f}", f"{np.sqrt(var):.1f}", f"{share:.0%}", "-", "-"])
    lines += ["## Takım sayısındaki hata nereden geliyor?", "", "Her takım-maç için gerçek ile simülasyon ortalaması arasındaki sayı farkı. Şans sütunu, atılan şut sayısıyla salt rastlantının üreteceği dağılım. Açıklanamayan pay, bunun üzerinde kalan dağılımın oranı: model burada bir şey kaçırıyor olabilir.", ""]
    lines += table(rows, ["Bileşen", "Ortalama", "SD", "Toplam varyansa oran", "Şans SD", "Şansla açıklanamayan"])

    # team stats against a team's own average so far
    rows = []
    long_rows = []
    for name, team in (("h", "home"), ("a", "away")):
        part = pd.DataFrame({"season": g.season, "date": g.date, "team": g[team]})
        for k in TEAM_STATS:
            part[f"{k}_sim"], part[f"{k}_real"], part[f"{k}_in80"] = g[f"{name}_{k}_sim"], g[f"{name}_{k}_real"], g[f"{name}_{k}_in80"]
        long_rows.append(part)
    long = pd.concat(long_rows, ignore_index=True).sort_values("date")
    for k in ("pts", "poss", "fga", "f3a", "inside_a", "mid_a", "fta", "tov", "orb", "drb", "ast", "stl", "blk", "pf"):
        avg = long.groupby(["season", "team"])[f"{k}_real"].transform(lambda v: v.shift().expanding().mean())
        ok = avg.notna()
        rows.append([k, f"{long[f'{k}_sim'].mean():.1f}", f"{long[f'{k}_real'].mean():.1f}", f"{(long[f'{k}_sim'] - long[f'{k}_real'])[ok].abs().mean():.2f}",
                     f"{(avg - long[f'{k}_real'])[ok].abs().mean():.2f}", f"{long[f'{k}_sim'][ok].corr(long[f'{k}_real'][ok]):.2f}", f"{avg[ok].corr(long[f'{k}_real'][ok]):.2f}", f"{long[f'{k}_in80'].mean():.0%}"])
    lines += ["", "## Takım istatistikleri", "", "Ortalama hatası: takımın o güne kadarki sezon ortalaması tahmin olarak kullanılsaydı çıkacak hata.", ""]
    lines += table(rows, ["İstatistik", "Simülasyon", "Gerçek", "Hata", "Ortalama hatası", "Korelasyon", "Ortalama korelasyonu", "%80 aralıkta"])

    # players
    rows = []
    for k, scale in (("sec", 60.0), ("pts", 1.0), ("f3a", 1.0), ("f2a", 1.0), ("fta", 1.0), ("orb", 1.0), ("drb", 1.0), ("ast", 1.0), ("tov", 1.0), ("stl", 1.0), ("blk", 1.0), ("pf", 1.0)):
        ok = pl[f"{k}_avg"].notna() & pl[f"{k}_last5"].notna()
        r = pl[ok]
        rows.append([k if k != "sec" else "dakika", f"{(r[f'{k}_sim'] - r[f'{k}_real']).abs().mean() / scale:.3f}", f"{(r[f'{k}_avg'] - r[f'{k}_real']).abs().mean() / scale:.3f}",
                     f"{(r[f'{k}_last5'] - r[f'{k}_real']).abs().mean() / scale:.3f}", f"{(r[f'{k}_sim'] - r[f'{k}_real']).mean() / scale:+.3f}", f"{r[f'{k}_in80'].mean():.0%}"])
    lines += ["", "## Oyuncu tahminleri", "", f"{int((pl.pts_avg.notna()).sum())} oyuncu-maç. Karşılaştırma: sezon ortalaması ve son 5 maç ortalaması.", ""]
    lines += table(rows, ["İstatistik", "Simülasyon hatası", "Sezon ortalaması", "Son 5 maç", "Sapma", "%80 aralıkta"])

    def player_cut(column):
        out = []
        groups = pl.groupby(column, observed=True)
        for key, r in groups:
            r = r[r.pts_avg.notna() & r.pts_last5.notna()]
            if len(r) < 30:
                continue
            out.append([key, len(r), f"{(r.sec_sim - r.sec_real).mean() / 60:+.2f}", f"{(r.sec_sim - r.sec_real).abs().mean() / 60:.2f}", f"{(r.sec_avg - r.sec_real).abs().mean() / 60:.2f}",
                        f"{(r.pts_sim - r.pts_real).mean():+.2f}", f"{(r.pts_sim - r.pts_real).abs().mean():.2f}", f"{(r.pts_avg - r.pts_real).abs().mean():.2f}", f"{(r.pts_last5 - r.pts_real).abs().mean():.2f}"])
        return out

    header = ["Kesit", "Oyuncu-maç", "Dakika sapması", "Dakika hatası", "Ort. dakika hatası", "Sayı sapması", "Sayı hatası", "Ort. sayı hatası", "Son 5 sayı hatası"]
    for title, col in (("Pozisyon", "position"), ("İlk beş mi", "starter"), ("Kullanım düzeyi", "usage_tier"), ("Takımdaki maç sayısı", "games_tier"), ("Ev ve deplasman", "where")):
        lines += ["", f"### {title}", ""]
        lines += table(player_cut(col), header)

    # systematic team error: does the model keep missing the same teams?
    e = gaps.assign(season_team=gaps.season + " " + gaps.team)
    tm = e.groupby("season_team").total.agg(["mean", "sem", "size"]).sort_values("mean")
    tm = tm[tm["size"] >= 8]
    z = tm["mean"] / tm["sem"]
    rows = [[k, f"{v['mean']:+.1f}", f"{v['sem']:.1f}", int(v["size"])] for k, v in tm.iloc[list(range(4)) + list(range(-4, 0))].iterrows()]
    lines += ["", "## Modelin sürekli yanıldığı takımlar", "", f"Gerçek eksi simülasyon, takım sayısı. Şans tek başına olsaydı değerlerin yaklaşık %5'i 2 standart hatayı aşardı; burada {(z.abs() > 2).mean():.0%}.", ""]
    lines += table(rows, ["Takım", "Ortalama fark", "SE", "Maç"])
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--sims", type=int, default=400)
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--likely", action="store_true", help="guess the squads from recent games, as for a game not played yet")
    a = ap.parse_args()
    t = load_tables()
    all_games = games_table()
    tag = "_likely" if a.likely else ""
    GAMES_FILE, PLAYERS_FILE, ENRICHED_FILE = (AUDIT_DIR / f"match_scorecard{tag}_{name}.parquet" for name in ("games", "players", "enriched"))
    if not a.report_only:
        path = LIKELY_CACHE if a.likely else CACHE
        games = prepare(t, a.likely) if a.rebuild or not path.exists() else pickle.loads(path.read_bytes())
        league = load_league()
        with ProcessPoolExecutor(8) as pool:
            results = list(pool.map(_simulate, [(x, league, a.sims) for x in games], chunksize=4))
        pd.DataFrame([r for r, _ in results]).to_parquet(GAMES_FILE, index=False)
        pd.DataFrame([p for _, ps in results for p in ps]).to_parquet(PLAYERS_FILE, index=False)

    g = pd.read_parquet(GAMES_FILE).merge(all_games[["season", "gamecode", "phase", "round", "date"]], on=["season", "gamecode"])
    g["home_won"] = g.h_pts_real > g.a_pts_real

    # net rating needs a finished season before it, so E2024 only trains it
    played = all_games[all_games.season.isin(("E2024", *SEASONS))]
    net = net_rating_probabilities(played, NetRatings(t.possessions, played))
    g["p_net"] = [net.get((s, c), np.nan) for s, c in zip(g.season, g.gamecode)]
    nets = NetRatings(t.possessions, played)
    g["net_gap"] = [nets.before(r.season, r.date).get(r.home, 0.0) - nets.before(r.season, r.date).get(r.away, 0.0) for r in g.itertuples()]

    # rest: days since each side's previous game
    long = pd.concat([all_games[["season", "gamecode", "date", "home"]].rename(columns={"home": "team"}), all_games[["season", "gamecode", "date", "away"]].rename(columns={"away": "team"})]).sort_values("date")
    long["rest"] = long.groupby(["season", "team"]).date.diff().dt.total_seconds() / 86400
    rest = long.set_index(["season", "gamecode", "team"]).rest
    g["rest_home"] = [rest.get((s, c, t_), np.nan) for s, c, t_ in zip(g.season, g.gamecode, g.home)]
    g["rest_away"] = [rest.get((s, c, t_), np.nan) for s, c, t_ in zip(g.season, g.gamecode, g.away)]
    g["rest_gap"] = (g.rest_home - g.rest_away).round()

    g.to_parquet(ENRICHED_FILE, index=False)

    pl = pd.read_parquet(PLAYERS_FILE)
    base = player_averages(t.player_games[t.player_games.season.isin(("E2024", *SEASONS))], {k: v for k, v in PLAYER_STATS.items()})
    for c in base.columns:
        if c.startswith("sec_"):
            base[c] = base[c] * 60  # minutes into the simulator's seconds
    pl = pl.merge(base, on=["season", "gamecode", "player_id"], how="left")
    pl["usage_tier"] = pd.cut(pl.usage, [0, 14, 20, 26, 100], labels=["düşük", "orta", "yüksek", "çok yüksek"]).astype(str)
    pl["games_tier"] = pd.cut(pl.games_before, [-1, 0, 5, 15, 100], labels=["0 maç", "1-5", "6-15", "16+"]).astype(str)
    pl["where"] = np.where(pl.side == 0, "ev", "deplasman")

    out = report(g, pl)
    if a.likely:
        out += (f"\n## Tahmini kadro\n\nKadro ve ilk beş son 4 maçtan tahmin edildi. İlk beşte isabet {g.starters_right.mean():.0%}, "
                f"maç başına gerçekte süre alıp tahminde olmayan oyuncu dakikası {g.real_minutes_missing.mean():.1f} (iki takım, toplam 400 dakikada).\n")
    (AUDIT_DIR / f"match_scorecard{tag}.md").write_text(out, encoding="utf-8")
    print(out.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
