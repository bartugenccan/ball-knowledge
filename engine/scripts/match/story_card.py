"""Does a simulated game read like a real one? The things a viewer would call out.

    uv run python scripts/match/story_card.py [--sims 400] [--set name=value ...]

The score is mostly chance, the story much less so. Who closes the game, when the main players rest,
who gets the points, the shape of the quarters and whether a team plays like itself can all be checked
against the real games, each one simulated from before it was played. The plain benchmark is what a
player or team had done so far that season.

Writes data/audit/match_story_card.md.
"""

from __future__ import annotations

import argparse
import pickle
import warnings
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scorecard import CACHE  # noqa: E402

from bk.config import AUDIT_DIR, TABLES_DIR  # noqa: E402
from bk.match.model import load_league  # noqa: E402
from bk.match.runner import run_many  # noqa: E402
from bk.match.sim import Tuning  # noqa: E402

PART = ("q1", "q2", "q3", "q4", "late")
PART_RANGE = {"q1": (0, 600), "q2": (600, 1200), "q3": (1200, 1800), "q4": (1800, 2400), "late": (2100, 2400)}
CLOSE_AT_END = 12       # a game this close with five minutes left still has real closers
STYLE = {"poss": "Hücum sayısı", "three_share": "Üçlük payı", "inside_share": "Boyalı alan payı", "mid_share": "Orta mesafe payı", "transition": "Geçiş şutu payı",
         "ftr": "Çizgiye gitme", "tov_rate": "Top kaybı", "orb_rate": "Hücum ribaundu", "assist_rate": "Asistli isabet payı", "depth": "10+ dakika alan oyuncu", "top5": "İlk 5'in dakika payı"}


def simulate(args) -> dict:
    game, league, tune, sims = args
    m = run_many(game["home"], game["away"], league, tune, sims, seed=game["gamecode"] * 1000 + int(game["season"][1:]))
    cols = m.box_columns
    out = {"season": game["season"], "gamecode": game["gamecode"], "players": [], "teams": [], "quarters": []}
    out["quarters"] = np.diff(m.quarters, axis=1, prepend=0).mean(axis=0).tolist()
    for side, team in ((0, m.home), (1, m.away)):
        pts = m.players[side][:, :, cols.index("pts")]
        sec = m.players[side][:, :, cols.index("sec")]
        parts = m.player_parts[side]
        top_share = (pts.max(axis=1) / pts.sum(axis=1).clip(min=1)).mean()
        t = m.team[side]
        fga = t["fga"].clip(min=1)
        other = m.team[1 - side]
        out["teams"].append({"team": team.code, "side": side, "top_share": float(top_share), "double_digit": float((pts >= 10).sum(axis=1).mean()),
                             "poss": float(t["poss"].mean()), "three_share": float((t["f3a"] / fga).mean()), "inside_share": float((t["inside_a"] / fga).mean()), "mid_share": float((t["mid_a"] / fga).mean()),
                             "transition": float((m.transition[side] / fga).mean()), "ftr": float((t["fta"] / fga).mean()), "tov_rate": float((t["tov"] / t["poss"].clip(min=1)).mean()),
                             "orb_rate": float((t["orb"] / (t["orb"] + other["drb"]).clip(min=1)).mean()), "assist_rate": float((t["ast"] / (t["f2m"] + t["f3m"]).clip(min=1)).mean()),
                             "depth": float((sec >= 600).sum(axis=1).mean()), "top5": float((np.sort(sec, axis=1)[:, -5:].sum(axis=1) / sec.sum(axis=1).clip(min=1)).mean())})
        for j, p in enumerate(team.players):
            row = {"player_id": p.player_id, "team": team.code, "pts_sim": float(pts[:, j].mean()), "sec_sim": float(sec[:, j].mean())}
            for k, name in enumerate(PART):
                row[f"{name}_sim"] = float(parts[:, j, k].mean())
            out["players"].append(row)
    return out


def real_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Real seconds in each part of the game per player, and the team numbers read the same way."""
    st = pd.read_parquet(TABLES_DIR / "stints.parquet", columns=["season", "gamecode", "team", "player_id", "start", "end"])
    st = st[st.season.isin(("E2025", "E2026"))]
    frames = []
    for name, (a, b) in PART_RANGE.items():
        sec = (st.end.clip(upper=b) - st.start.clip(lower=a)).clip(lower=0)
        frames.append(st.assign(sec=sec).groupby(["season", "gamecode", "team", "player_id"]).sec.sum().rename(f"{name}_real"))
    parts = pd.concat(frames, axis=1).fillna(0.0).reset_index()

    pg = pd.read_parquet(TABLES_DIR / "player_games.parquet", columns=["season", "gamecode", "date", "team", "player_id", "pts", "minutes", "fg2a", "fg3a", "fg2m", "fg3m", "fta", "tov", "orb", "drb", "ast"])
    pg = pg[pg.season.isin(("E2025", "E2026"))]
    shots = pd.read_parquet(TABLES_DIR / "shots.parquet", columns=["season", "gamecode", "team", "zone_group", "context"])
    shots = shots[shots.season.isin(("E2025", "E2026"))]
    po = pd.read_parquet(TABLES_DIR / "possessions.parquet", columns=["season", "gamecode", "offense"])
    keys = ["season", "gamecode", "team"]
    t = pg.groupby(keys).agg(fga2=("fg2a", "sum"), fga3=("fg3a", "sum"), made=("fg2m", "sum"), made3=("fg3m", "sum"), fta=("fta", "sum"), tov=("tov", "sum"), orb=("orb", "sum"), drb=("drb", "sum"), ast=("ast", "sum"), pts=("pts", "sum")).reset_index()
    t["fga"] = t.fga2 + t.fga3
    t["makes"] = t.made + t.made3
    t = t.merge(po.groupby(["season", "gamecode", "offense"]).size().rename("poss").reset_index().rename(columns={"offense": "team"}), on=keys)
    sh = shots.groupby(keys).agg(inside=("zone_group", lambda v: (v == "inside").sum()), mid=("zone_group", lambda v: (v == "mid").sum()), trans=("context", lambda v: (v == "transition").sum())).reset_index()
    t = t.merge(sh, on=keys)
    opp = t[["season", "gamecode", "team", "drb"]].rename(columns={"team": "other", "drb": "other_drb"})
    t = t.merge(opp, on=["season", "gamecode"])
    t = t[t.team != t.other]
    t["three_share"], t["inside_share"], t["mid_share"], t["transition"] = t.fga3 / t.fga, t.inside / t.fga, t.mid / t.fga, t.trans / t.fga
    t["ftr"], t["tov_rate"], t["orb_rate"], t["assist_rate"] = t.fta / t.fga, t.tov / t.poss, t.orb / (t.orb + t.other_drb), t.ast / t.makes
    g = pg[pg.minutes > 0].sort_values("minutes", ascending=False).groupby(keys)
    t = t.merge(g.minutes.apply(lambda v: float((v >= 10).sum())).rename("depth").reset_index(), on=keys)
    t = t.merge(g.minutes.apply(lambda v: float(v.head(5).sum() / v.sum())).rename("top5").reset_index(), on=keys)
    top = pg.groupby(keys).pts.agg(lambda v: float(v.max() / max(v.sum(), 1))).rename("top_share").reset_index()
    t = t.merge(top, on=keys)
    t = t.merge(pg[pg.pts >= 10].groupby(keys).size().rename("double_digit").reset_index(), on=keys, how="left").fillna({"double_digit": 0})
    players = pg[["season", "gamecode", "date", "team", "player_id", "pts", "minutes"]].merge(parts, on=["season", "gamecode", "team", "player_id"], how="left").fillna(0.0)
    return players, t


def season_so_far(pl: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Each player's average before the game, from the games he played."""
    d = pl.sort_values(["player_id", "season", "date"]).copy()
    played = d.minutes > 0
    for c in columns:
        values = d[c].where(played)
        d[f"{c}_avg"] = values.groupby([d.season, d.player_id]).transform(lambda v: v.shift().expanding().mean())
    return d


def overlap(a: pd.Series, b: pd.Series, players: pd.Series, n: int = 5) -> float:
    return len(set(players[a.nlargest(n).index]) & set(players[b.nlargest(n).index])) / n


def card(results: list[dict], real_p: pd.DataFrame, real_t: pd.DataFrame) -> dict:
    sim_p = pd.concat([pd.DataFrame(r["players"]).assign(season=r["season"], gamecode=r["gamecode"]) for r in results], ignore_index=True)
    columns = ["pts", *[f"{n}_real" for n in PART]]
    base = season_so_far(real_p, columns)
    d = sim_p.merge(base, on=["season", "gamecode", "team", "player_id"], how="left")
    d = d[d.minutes.notna()]
    out: dict = {}

    # who plays in which part of the game
    known = d[d.q1_real_avg.notna()]
    out["parts"] = {name: {"sim": float((known[f"{name}_sim"] - known[f"{name}_real"]).abs().mean() / 60), "avg": float((known[f"{name}_real_avg"] - known[f"{name}_real"]).abs().mean() / 60),
                           "bias": float((known[f"{name}_sim"] - known[f"{name}_real"]).mean() / 60)} for name in PART}

    # who closes: in close games, how many of the real last five minutes' main five did we name?
    sim_rows, base_rows = [], []
    closes = 0
    for (season, code, team), g in known.groupby(["season", "gamecode", "team"]):
        if len(g) < 5 or g.late_real.max() < 120:
            continue
        closes += 1
        sim_rows.append(overlap(g.late_sim, g.late_real, g.player_id))
        base_rows.append(overlap(g.late_real_avg, g.late_real, g.player_id))
    out["closers"] = {"sim": float(np.mean(sim_rows)), "avg": float(np.mean(base_rows)), "n": closes}

    # who gets the points
    tops = {"sim1": [], "avg1": [], "sim3": [], "avg3": []}
    for _, g in d[d.pts_avg.notna()].groupby(["season", "gamecode", "team"]):
        real_top = g.player_id[g.pts.idxmax()]
        sim_rank = g.nlargest(3, "pts_sim").player_id.tolist()
        avg_rank = g.nlargest(3, "pts_avg").player_id.tolist()
        tops["sim1"].append(sim_rank[0] == real_top)
        tops["avg1"].append(avg_rank[0] == real_top)
        tops["sim3"].append(real_top in sim_rank)
        tops["avg3"].append(real_top in avg_rank)
    out["top_scorer"] = {k: float(np.mean(v)) for k, v in tops.items()}

    teams = pd.concat([pd.DataFrame(r["teams"]).assign(season=r["season"], gamecode=r["gamecode"]) for r in results], ignore_index=True)
    t = teams.merge(real_t, on=["season", "gamecode", "team"], suffixes=("_sim", "_real"))
    out["share"] = {k: {"sim": float(t[f"{k}_sim"].mean()), "real": float(t[f"{k}_real"].mean())} for k in ("top_share", "double_digit")}

    # does a team play like itself: across team-seasons, simulated against real
    # a full season only: nine games of E2026 would add noise to the real spread between teams
    agg = t[t.season == "E2025"].groupby("team")[[f"{k}_{s}" for k in STYLE for s in ("sim", "real")]].mean()
    out["style"] = {k: {"corr": float(agg[f"{k}_sim"].corr(agg[f"{k}_real"])), "sim": float(agg[f"{k}_sim"].mean()), "real": float(agg[f"{k}_real"].mean()), "spread_sim": float(agg[f"{k}_sim"].std()), "spread_real": float(agg[f"{k}_real"].std())} for k in STYLE}

    # the shape of a game
    g = pd.read_parquet(TABLES_DIR / "events.parquet", columns=["season", "gamecode", "period", "type", "team"])
    g = g[g.season.isin(("E2025", "E2026")) & g.type.isin(["2FGM", "3FGM", "FTM"]) & (g.period <= 4)]
    g["pts"] = g.type.map({"2FGM": 2, "3FGM": 3, "FTM": 1})
    q = g.groupby(["season", "gamecode", "period"]).pts.sum().unstack().mean(axis=0) / 2
    sim_q = np.mean([np.mean(r["quarters"], axis=1) for r in results], axis=0)
    out["quarters"] = {"real": [float(x) for x in q], "sim": [float(x) for x in sim_q]}
    return out


def write(base: dict, new: dict | None) -> str:
    n = new or base
    lines = ["# Hikâye karnesi", "", "Bir izleyicinin \"bu maç böyle geçmez\" diyeceği şeyler. Her maç kendinden önceki veriyle oynatıldı. Kıyas: oyuncu ya da takımın o güne kadarki sezon ortalaması.", ""]
    head = ["Ölçüm", "Başlangıç modeli", *(["Yeni model"] if new else []), "Sezon ortalaması"]

    def row(label: str, a: str, b: str | None, c: str) -> str:
        return "| " + " | ".join([label, a, *([b] if new else []), c]) + " |"

    lines += ["## Maçı kim bitiriyor?", "", f"Son 5 dakikada en çok oynayan beşlinin kaçını doğru bildik ({n['closers']['n']} takım-maç).", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head),
              row("Beşlide isabet", f"{base['closers']['sim']:.0%}", f"{n['closers']['sim']:.0%}", f"{n['closers']['avg']:.0%}"), ""]
    lines += ["## Kim ne zaman oynuyor?", "", "Maçın her bölümünde oyuncu başına dakika hatası.", "", "| " + " | ".join(head) + " | Yeni sapma |", "|" + "---|" * (len(head) + 1)]
    labels = {"q1": "1. çeyrek", "q2": "2. çeyrek", "q3": "3. çeyrek", "q4": "4. çeyrek", "late": "Son 5 dakika"}
    for k, text in labels.items():
        lines.append(row(text, f"{base['parts'][k]['sim']:.2f}", f"{n['parts'][k]['sim']:.2f}", f"{n['parts'][k]['avg']:.2f}") + f" {n['parts'][k]['bias']:+.2f} |")
    lines += ["", "## Sayıyı kim atıyor?", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head),
              row("Takımın en skorer ismini doğru bilme", f"{base['top_scorer']['sim1']:.0%}", f"{n['top_scorer']['sim1']:.0%}", f"{n['top_scorer']['avg1']:.0%}"),
              row("Gerçek en skorer, beklenen ilk 3'te", f"{base['top_scorer']['sim3']:.0%}", f"{n['top_scorer']['sim3']:.0%}", f"{n['top_scorer']['avg3']:.0%}"), "",
              f"En skorer oyuncunun takım sayısındaki payı: simülasyon {n['share']['top_share']['sim']:.1%}, gerçek {n['share']['top_share']['real']:.1%}. Çift haneli sayı atan oyuncu: simülasyon {n['share']['double_digit']['sim']:.2f}, gerçek {n['share']['double_digit']['real']:.2f}.", ""]
    lines += ["## Takım kendisi gibi mi oynuyor?", "", "E2025'in tam sezonunda, takım düzeyinde simülasyon ile gerçeğin korelasyonu. Dağılım: takımlar arası farkın ne kadarı korunuyor.", "", "| Stil | Korelasyon | Simülasyon ort. | Gerçek ort. | Sim. takım farkı | Gerçek takım farkı |", "|---|---:|---:|---:|---:|---:|"]
    for k, text in STYLE.items():
        s = n["style"][k]
        lines.append(f"| {text} | {s['corr']:.2f} | {s['sim']:.3f} | {s['real']:.3f} | {s['spread_sim']:.3f} | {s['spread_real']:.3f} |")
    lines += ["", "## Çeyreklerin şekli", "", "Takım başına çeyrek sayısı.", "", "| | 1 | 2 | 3 | 4 |", "|---|---:|---:|---:|---:|",
              "| Gerçek | " + " | ".join(f"{x:.1f}" for x in n["quarters"]["real"]) + " |", "| Simülasyon | " + " | ".join(f"{x:.1f}" for x in n["quarters"]["sim"]) + " |", ""]
    return "\n".join(lines) + "\n"


def run(games, league, tune, sims):
    with ProcessPoolExecutor(8) as pool:
        return list(pool.map(simulate, [(g, league, tune, sims) for g in games], chunksize=4))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=400)
    ap.add_argument("--set", nargs="*", default=[])
    a = ap.parse_args()
    games = pickle.loads(CACHE.read_bytes())
    league = load_league()
    real_p, real_t = real_tables()
    start = Tuning(max_centers=1.0, team_strength=0.0, usage_power=1.0, recent_minutes=0.0, closer_weight=0.0, orb_team_scale=0.0, tempo_scale=1.0, transition_scale=1.0)
    base = card(run(games, league, start, a.sims), real_p, real_t)
    changes = {k: float(v) for k, v in (x.split("=") for x in a.set)}
    new = card(run(games, league, replace(Tuning(), **changes), a.sims), real_p, real_t)
    text = write(base, new)
    (AUDIT_DIR / "match_story_card.md").write_text(text, encoding="utf-8")
    print(text.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
