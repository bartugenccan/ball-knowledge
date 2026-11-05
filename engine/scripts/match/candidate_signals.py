"""Is there a real signal behind each idea, before it goes anywhere near the simulator?

    uv run python scripts/match/candidate_signals.py

Every test fits on E2025 (or an earlier season) and checks on E2026. An idea that fails stays out,
however reasonable it sounds. The rule is fixed here, before the results:

    SURVIVES if the effect is at least 2 standard errors from zero where it was fitted,
    points the same way on E2026, and any placebo stays flat.

Writes data/audit/match_candidate_signals.md.
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from bk.config import AUDIT_DIR, TABLES_DIR  # noqa: E402
from bk.sim.calibrate import fit_slope  # noqa: E402

ZONES = ("inside", "mid", "corner3", "above_break3")
EDGE = {"inside": "rel_inside_adj", "mid": "rel_mid_pct", "corner3": "rel_corner3_pct", "above_break3": "rel_three_pct"}
ORDER = {"Guard": 0, "Forward": 1, "Center": 2}
FIT, CHECK = "E2025", "E2026"
K_POSITION = 300.0
K_VENUE_GAMES = 15.0


def verdict(b_fit: float, se_fit: float, b_check: float, placebo: float | None = None, placebo_se: float | None = None) -> str:
    ok = abs(b_fit) >= 2 * se_fit and np.sign(b_fit) == np.sign(b_check)
    if placebo is not None and abs(placebo) >= 2 * placebo_se:
        ok = False
    return "YAŞADI" if ok else "ÇÜRÜDÜ"


def load_shots() -> pd.DataFrame:
    s = pd.read_parquet(TABLES_DIR / "shots.parquet", columns=["season", "gamecode", "date", "team", "opponent", "player_id", "made", "zone_group", "context", "off_lineup", "def_lineup", "lineup_ok"])
    s = s[s.zone_group.isin(ZONES) & s.lineup_ok].copy()
    m = pd.read_parquet(TABLES_DIR / "player_metrics.parquet", columns=["season", "player_id", *EDGE.values(), "three_rate", "mid_rate", "inside_rate"])
    s = s.merge(m, on=["season", "player_id"], how="left")
    level = s.groupby(["season", "zone_group", "context"]).made.transform("mean")
    edge = np.select([s.zone_group == z for z in ZONES], [s[EDGE[z]].fillna(0.0) for z in ZONES])
    s["expected"] = np.clip(level + edge, 0.05, 0.95)
    s["offset"] = np.log(s.expected / (1 - s.expected))
    s["y"] = s.made.astype(float)
    return s


def test_venue(lines: list[str]) -> None:
    """Do clubs differ in home advantage? Each club's home net rating minus its road net rating."""
    po = pd.read_parquet(TABLES_DIR / "possessions.parquet", columns=["season", "gamecode", "offense", "defense", "points"])
    g = pd.read_parquet(TABLES_DIR / "games.parquet", columns=["season", "gamecode", "home", "away", "date"])
    x = po.merge(g, on=["season", "gamecode"])
    rows = []
    for (season, gamecode, home, away), part in x.groupby(["season", "gamecode", "home", "away"]):
        h, a = part[part.offense == home].points, part[part.offense == away].points
        margin = 100 * (h.mean() - a.mean())
        rows.append({"season": season, "gamecode": gamecode, "team": home, "at_home": True, "net": margin})
        rows.append({"season": season, "gamecode": gamecode, "team": away, "at_home": False, "net": -margin})
    d = pd.DataFrame(rows).merge(g[["season", "gamecode", "date"]], on=["season", "gamecode"]).sort_values("date")
    d["i"] = d.groupby(["season", "team", "at_home"]).cumcount()

    def gap(frame: pd.DataFrame) -> pd.Series:
        t = frame.groupby(["team", "at_home"]).net.mean().unstack()
        return (t[True] - t[False]) / 2

    lines += ["## Kulübe özgü iç saha avantajı", "", "Kulübün iç sahadaki net reytingi ile deplasmandaki net reytingi arasındaki farkın yarısı. Lig ortalaması her kulüpte zaten var. Soru: kulüpler bunda kalıcı olarak ayrışıyor mu?", ""]
    same = {}
    for season in ("E2024", "E2025"):
        part = d[d.season == season]
        same[season] = float(gap(part[part.i % 2 == 0]).corr(gap(part[part.i % 2 == 1])))
    gaps = {s: gap(d[d.season == s]) for s in ("E2024", "E2025", "E2026")}
    next_24 = float(gaps["E2024"].corr(gaps["E2025"]))
    next_25 = float(gaps["E2025"].corr(gaps["E2026"]))
    per_game = d[d.season.isin(("E2024", "E2025"))].groupby(["season", "team", "at_home"]).net
    spread = float(np.sqrt((per_game.var() / per_game.size()).groupby(["season", "team"]).sum().mean()) / 2)
    observed = float(pd.concat([gaps["E2024"], gaps["E2025"]]).std())
    true_sd = float(np.sqrt(max(observed ** 2 - spread ** 2, 0)))
    lines += [f"- Sezon içi kararlılık (tek ve çift maçlar): E2024 {same['E2024']:+.2f}, E2025 {same['E2025']:+.2f}",
              f"- Sezondan sezona: E2024→E2025 {next_24:+.2f}, E2025→E2026 {next_25:+.2f}",
              f"- Kulüpler arasındaki gözlenen dağılım SD {observed:.1f} (100 hücumda). Salt şansın üreteceği {spread:.1f}. Gerçek kulüp farkı tahmini SD {true_sd:.1f}.", ""]

    # the part that matters: does a club's venue record so far predict the model's error tonight?
    e = pd.read_parquet(AUDIT_DIR / "match_scorecard_enriched.parquet").sort_values("date")
    e["err"] = (e.h_pts_real - e.a_pts_real) - (e.h_pts_sim - e.a_pts_sim)
    home_sum: dict = {}
    away_sum: dict = {}
    signals = []
    for r in e.itertuples():
        def venue(team: str) -> float:
            hs, hn = home_sum.get((r.season, team), (0.0, 0))
            an_s, an_n = away_sum.get((r.season, team), (0.0, 0))
            # half the gap between how far the model is off at home and on the road, pulled toward zero
            return 0.5 * (hs / (hn + K_VENUE_GAMES) - an_s / (an_n + K_VENUE_GAMES))
        signals.append(venue(r.home) + venue(r.away))
        hs, hn = home_sum.get((r.season, r.home), (0.0, 0))
        home_sum[(r.season, r.home)] = (hs + r.err, hn + 1)
        an_s, an_n = away_sum.get((r.season, r.away), (0.0, 0))
        away_sum[(r.season, r.away)] = (an_s - r.err, an_n + 1)
    e["venue"] = signals
    train, test = e[e.season == FIT], e[e.season == CHECK]
    beta = float((train.venue * train.err).sum() / (train.venue ** 2).sum())
    se = float(np.sqrt(((train.err - beta * train.venue) ** 2).mean() / (train.venue ** 2).sum()))
    beta_check = float((test.venue * test.err).sum() / (test.venue ** 2).sum()) if (test.venue ** 2).sum() > 0 else 0.0
    before, after = np.sqrt((test.err ** 2).mean()), np.sqrt(((test.err - beta * test.venue) ** 2).mean())
    lines += [f"Maç öncesi kulüp iç saha kaydının, modelin o maçtaki hatasını öngörmesi: eğim E2025'te {beta:+.2f} (SE {se:.2f}), E2026'da {beta_check:+.2f}. E2026 RMSE {before:.2f} → {after:.2f}.",
              "", f"**Karar: {verdict(beta, se, beta_check)}.**", ""]

    # the plain record, which is worth showing whatever the verdict
    recent = d[d.season.isin(("E2025", "E2026"))]
    t = recent.groupby(["team", "at_home"]).net.agg(["mean", "size", "sem"]).unstack()
    table = pd.DataFrame({"home": t["mean"][True], "road": t["mean"][False], "gap": (t["mean"][True] - t["mean"][False]) / 2,
                          "se": np.sqrt(t["sem"][True] ** 2 + t["sem"][False] ** 2) / 2, "games": t["size"][True] + t["size"][False]}).dropna().sort_values("gap", ascending=False)
    lines += ["Kulüplerin kaydı (E2025 ve E2026): 100 hücumda net fark.", "", "| Kulüp | İç saha | Deplasman | Avantaj (yarı fark) | SE | Maç |", "|---|---:|---:|---:|---:|---:|"]
    lines += [f"| {k} | {v.home:+.1f} | {v.road:+.1f} | {v.gap:+.1f} | {v.se:.1f} | {int(v.games)} |" for k, v in table.iterrows()]
    lines += [f"| Lig ortalaması | | | {table.gap.mean():+.1f} | | |", ""]


def test_matchup(s: pd.DataFrame, lines: list[str]) -> None:
    """Does the defender a position and height assignment names change the shot, against a placebo?"""
    people = pd.read_parquet(TABLES_DIR / "people.parquet", columns=["season", "player_id", "position", "height"])
    info = {(r.season, r.player_id): (ORDER.get(r.position, 1), float(r.height) if r.height == r.height and r.height else 200.0) for r in people.itertuples()}
    ratings = pd.read_parquet(TABLES_DIR / "ratings_season.parquet", columns=["season", "player_id", "perimeter_defense", "rim_protection"])
    by_season = {(r.season, r.player_id): (r.perimeter_defense, r.rim_protection) for r in ratings.itertuples()}

    def run(season: str, zones: tuple[str, ...], which: int) -> tuple[float, float, float, float, int]:
        past = f"E{int(season[1:]) - 1}"
        part = s[(s.season == season) & s.zone_group.isin(zones)]
        x, placebo, y, offset = [], [], [], []
        for r in part.itertuples():
            rank = lambda p: (*info.get((season, p), (1, 200.0)), p)  # noqa: E731
            off = sorted(r.off_lineup, key=rank)
            if r.player_id not in off or len(off) != 5 or len(r.def_lineup) != 5:
                continue
            dfn = sorted(r.def_lineup, key=rank)
            vals = [by_season.get((past, p)) for p in dfn]
            known = [v[which] for v in vals if v is not None]
            if len(known) < 3:
                continue
            fill = float(np.mean(known))
            vals = [v[which] if v is not None else fill for v in vals]
            i = off.index(r.player_id)
            x.append((vals[i] - fill) / 3.2)
            placebo.append((vals[(i + 2) % 5] - fill) / 3.2)
            y.append(r.y)
            offset.append(r.offset)
        y_, o = np.array(y), np.array(offset)
        b, se = fit_slope(y_, o, np.array(x))
        pb, pse = fit_slope(y_, o, np.array(placebo))
        return b, se, pb, pse, len(y_)

    lines += ["## Bireysel eşleşme", "", "Pozisyon ve boya göre atanan savunmacının bir önceki sezondaki puanı (1 SD), şutçunun isabetine etkisi. Sahte: aynı beşlideki başka bir savunmacı. Eksi: savunmacı isabeti düşürüyor.", "",
              "| Şut | Savunma puanı | E2025 etki (SE) | E2025 sahte (SE) | E2026 etki (SE) | Şut (E2025) | Karar |", "|---|---|---:|---:|---:|---:|---|"]
    for label, zones, which, name in (("Üçlük", ("corner3", "above_break3"), 0, "Çevre Savunması"), ("Boyalı alan", ("inside",), 1, "Pota Koruma")):
        b, se, pb, pse, n = run(FIT, zones, which)
        b2, se2, _, _, _ = run(CHECK, zones, which)
        lines.append(f"| {label} | {name} | {b:+.3f} ({se:.3f}) | {pb:+.3f} ({pse:.3f}) | {b2:+.3f} ({se2:.3f}) | {n} | {verdict(b, se, b2, pb, pse)} |")
    lines += [""]


def test_position_defense(s: pd.DataFrame, lines: list[str]) -> None:
    """Does a team's record against a position so far predict tonight's shots by that position?"""
    people = pd.read_parquet(TABLES_DIR / "people.parquet", columns=["season", "player_id", "position"]).drop_duplicates(["season", "player_id"])
    d = s.merge(people, on=["season", "player_id"], how="left")
    d = d[d.position.isin(ORDER)].sort_values("date").copy()
    d["gap"] = d.y - d.expected
    games = d.groupby(["season", "gamecode", "opponent", "position"], sort=False).agg(gap=("gap", "sum"), n=("gap", "size")).reset_index()
    order = d.drop_duplicates(["season", "gamecode"]).reset_index(drop=True).reset_index()[["season", "gamecode", "index"]]
    games = games.merge(order, on=["season", "gamecode"]).sort_values("index")
    grouped = games.groupby(["season", "opponent", "position"])
    games["past_gap"] = grouped.gap.transform(lambda v: v.shift().fillna(0).cumsum())
    games["past_n"] = grouped.n.transform(lambda v: v.shift().fillna(0).cumsum())
    # the team's overall defense is already in the model, so only the difference between positions counts
    games["team_gap"] = games.groupby(["season", "opponent", "gamecode"]).past_gap.transform("sum")
    games["team_n"] = games.groupby(["season", "opponent", "gamecode"]).past_n.transform("sum")
    games["signal"] = games.past_gap / (games.past_n + K_POSITION) - games.team_gap / (games.team_n + 3 * K_POSITION)
    d = d.merge(games[["season", "gamecode", "opponent", "position", "signal"]], on=["season", "gamecode", "opponent", "position"], how="left")
    d["signal"] = d.signal.fillna(0.0) / 0.25   # percentage points to logits near the middle
    d_fit, d_check = d[d.season == FIT], d[d.season == CHECK]
    b, se = fit_slope(d_fit.y.to_numpy(), d_fit.offset.to_numpy(), d_fit.signal.to_numpy())
    b2, se2 = fit_slope(d_check.y.to_numpy(), d_check.offset.to_numpy(), d_check.signal.to_numpy())
    lines += ["## Pozisyona karşı savunma", "", "Takımın o güne kadar her pozisyona karşı isabet kaydının, takımın genel savunmasından farkı. 1'e yakın eğim, kaydın olduğu gibi geçerli olduğu anlamına gelir.", "",
              f"Eğim E2025'te {b:+.3f} (SE {se:.3f}), E2026'da {b2:+.3f} (SE {se2:.3f}).", "", f"**Karar: {verdict(b, se, b2)}.**", ""]


def test_usage(s: pd.DataFrame, lines: list[str]) -> None:
    """When the lineup around a player puts more of the shots on him, does he shoot worse?

    The lineup is the coach's choice, so this is cleaner than comparing nights when he simply shot more.
    """
    rate = {(r.season, r.player_id): r.three_rate + r.mid_rate + r.inside_rate for r in s.drop_duplicates(["season", "player_id"]).itertuples() if r.three_rate == r.three_rate}
    d = s.copy()
    share = []
    for r in d.itertuples():
        total = sum(rate.get((r.season, p), 10.0) for p in r.off_lineup)
        share.append(np.log(rate.get((r.season, r.player_id), 10.0) / total) if total else 0.0)
    d["log_share"] = share
    d["load"] = d.log_share - d.groupby(["season", "player_id"]).log_share.transform("mean")
    a, b = d[d.season == FIT], d[d.season == CHECK]
    fit, se = fit_slope(a.y.to_numpy(), a.offset.to_numpy(), a.load.to_numpy())
    check, se2 = fit_slope(b.y.to_numpy(), b.offset.to_numpy(), b.load.to_numpy())
    lines += ["## Kullanım ve verim dengesi", "", "Beşlide şut payının oyuncunun alışık olduğundan ne kadar büyük olduğu, isabete etkisi. Eksi: yük arttıkça verim düşüyor. Bu çıkarsa \"oyuncu olmasaydı\" sorusu da yanıtlanabilir.", "",
              f"Eğim E2025'te {fit:+.3f} (SE {se:.3f}), E2026'da {check:+.3f} (SE {se2:.3f}). Yükteki 1 SD: {a.load.std():.2f}.", "", f"**Karar: {verdict(fit, se, check)}.**", ""]


def test_playoffs(lines: list[str]) -> None:
    """Are play-off games really lower scoring and slower, in more than one season?"""
    po = pd.read_parquet(TABLES_DIR / "possessions.parquet", columns=["season", "gamecode", "points"])
    g = pd.read_parquet(TABLES_DIR / "games.parquet", columns=["season", "gamecode", "phase"])
    x = po.merge(g, on=["season", "gamecode"])
    x["late"] = x.phase != "RS"
    per_game = x.groupby(["season", "gamecode", "late"]).points.agg(["sum", "size"]).reset_index()
    rows = ["| Sezon | Normal sezon sayı/maç | Play-off sayı/maç | Fark (SE) | Hücum/maç farkı | Maç |", "|---|---:|---:|---:|---:|---:|"]
    diffs, ses = [], []
    for season in ("E2024", "E2025"):
        a, b = per_game[(per_game.season == season) & ~per_game.late], per_game[(per_game.season == season) & per_game.late]
        d, se = b["sum"].mean() - a["sum"].mean(), np.sqrt(b["sum"].var() / len(b) + a["sum"].var() / len(a))
        diffs.append(d)
        ses.append(se)
        rows.append(f"| {season} | {a['sum'].mean():.1f} | {b['sum'].mean():.1f} | {d:+.1f} ({se:.1f}) | {b['size'].mean() - a['size'].mean():+.1f} | {len(b)} |")
    ok = abs(diffs[0]) >= 2 * ses[0] and np.sign(diffs[0]) == np.sign(diffs[1])
    lines += ["## Play-off etkisi", "", "E2026'da henüz play-off yok, bu yüzden test E2024 ve E2025 arasında.", ""] + rows + ["", f"**Karar: {'YAŞADI' if ok else 'ÇÜRÜDÜ'}.**", ""]


def test_minutes(lines: list[str]) -> None:
    """Do recent minutes improve the pre-game minutes target?"""
    pl = pd.read_parquet(AUDIT_DIR / "match_scorecard_players.parquet")
    pg = pd.read_parquet(TABLES_DIR / "player_games.parquet", columns=["season", "gamecode", "date", "player_id", "minutes"]).sort_values("date")
    played = pg[pg.minutes > 0].copy()
    played["last3"] = played.groupby(["season", "player_id"]).minutes.transform(lambda v: v.shift().rolling(3, min_periods=1).mean())
    pl = pl.merge(played[["season", "gamecode", "player_id", "last3"]], on=["season", "gamecode", "player_id"], how="left")
    pl["real"] = pl.sec_real / 60
    d = pl[pl.last3.notna()]
    a, b = d[d.season == FIT], d[d.season == CHECK]
    best, best_mae = 0.0, float("inf")
    for w in np.arange(0, 1.01, 0.1):
        mae = float(((1 - w) * a.target + w * a.last3 - a.real).abs().mean())
        if mae < best_mae:
            best, best_mae = float(w), mae
    gaps = (a.target - a.real).abs() - ((1 - best) * a.target + best * a.last3 - a.real).abs()
    gain, se = float(gaps.mean()), float(gaps.std() / np.sqrt(len(gaps)))
    gain2 = float(((b.target - b.real).abs() - ((1 - best) * b.target + best * b.last3 - b.real).abs()).mean())
    lines += ["## Dakika tahmini", "", f"Hedef dakika, son 3 maçla %{100 * best:.0f} karıştırılınca. Karışım oranı E2025'te seçildi.", "",
              f"Hata E2025'te {a.target.sub(a.real).abs().mean():.3f} → {best_mae:.3f} (kazanç {gain:.3f}, SE {se:.3f}). E2026'da kazanç {gain2:+.3f}.", "",
              f"**Karar: {verdict(gain, se, gain2)}.**", ""]


def main() -> None:
    lines = ["# Adayların sinyal testleri", "", "Kural, sonuçlardan önce yazıldı: etki oturtulduğu sezonda en az 2 standart hata sıfırdan uzak olmalı, E2026'da aynı yönü göstermeli, sahte kontrol düz kalmalı. Geçemeyen simülatöre girmez.", ""]
    s = load_shots()
    test_venue(lines)
    test_matchup(s, lines)
    test_position_defense(s, lines)
    test_usage(s, lines)
    test_playoffs(lines)
    test_minutes(lines)
    out = "\n".join(lines) + "\n"
    (AUDIT_DIR / "match_candidate_signals.md").write_text(out, encoding="utf-8")
    print(out.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
