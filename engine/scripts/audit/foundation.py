"""Stage 1 audit of the data foundation. Read-only: it writes only under data/audit/.

    uv run python scripts/audit/foundation.py

Covers official reconciliation, feed-vs-box consistency, lineups, clock order,
cleaning flags, the coordinate bias test (T4), rebounds, free-throw trips, fouls,
blocks and roster data. Output: data/audit/foundation.md plus CSV detail files.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bk.config import AUDIT_DIR, TABLES_DIR
from bk.model.clean import FOUL_KINDS

GAME = ["season", "gamecode"]
PG = GAME + ["player_id"]
COUNT_STATS = ["pts", "fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta", "orb", "drb", "ast", "stl", "tov", "blk",
               "blk_against", "pf", "fd", "pir"]
MIN_ARENA_SHOTS = 200


def table(df: pd.DataFrame, index: bool = False) -> str:
    """Small GitHub-style Markdown table (no extra dependency)."""
    d = df.reset_index() if index else df
    rows = [[f"{v:,.3f}".rstrip("0").rstrip(".") if isinstance(v, (float, np.floating)) else f"{v}" for v in r]
            for r in d.itertuples(index=False)]
    head = "| " + " | ".join(map(str, d.columns)) + " |\n|" + "---|" * len(d.columns)
    return "\n".join([head] + ["| " + " | ".join(r) + " |" for r in rows])


def official_section(pg: pd.DataFrame, off: pd.DataFrame, out: list[str]) -> None:
    out.append("## 1. Resmi sezon toplamlarıyla karşılaştırma\n")
    if off.empty:
        out.append("Resmi toplam verisi yok.\n")
        return
    ours = pg.groupby(["season", "player_id"]).agg(
        games=("gamecode", "size"), minutes=("minutes", "sum"), **{c: (c, "sum") for c in COUNT_STATS}).reset_index()
    j = ours.merge(off, on=["season", "player_id"], how="outer", suffixes=("", "_off"), indicator=True)
    rows, detail = [], []
    for season, g in j.groupby("season"):
        both = g[g._merge == "both"]
        row = {"sezon": season, "bizde": int((g._merge != "right_only").sum()),
               "resmi": int((g._merge != "left_only").sum()),
               "yalnız_bizde": int((g._merge == "left_only").sum()),
               "yalnız_resmi": int((g._merge == "right_only").sum())}
        for c in ["games"] + COUNT_STATS:
            bad = both[(both[c] - both[f"{c}_off"]).abs() > 1e-6]
            row[c] = len(bad)
            detail += [{"season": season, "player_id": r.player_id, "stat": c, "ours": getattr(r, c),
                        "official": getattr(r, f"{c}_off")} for r in bad.itertuples()]
        d = (both.minutes - both.minutes_off).abs()
        row["dakika>1"] = int((d > 1).sum())
        detail += [{"season": season, "player_id": r.player_id, "stat": "minutes", "ours": r.minutes,
                    "official": r.minutes_off} for r in both[d > 1].itertuples()]
        rows.append(row)
    pd.DataFrame(detail).to_csv(AUDIT_DIR / "official_mismatches.csv", index=False)
    summary = pd.DataFrame(rows)
    out += ["Her sayı, o istatistikte resmi toplamdan farklı olan oyuncu sayısı.\n", table(summary), ""]
    games = pg[GAME].drop_duplicates().groupby("season").size()
    out.append(f"Kapsanan maç sayısı: {games.to_dict()}. Toplam fark satırı: {len(detail)}. Ayrıntı: `official_mismatches.csv`.\n")


def internal_section(pg, ev, sh, po, games, out: list[str]) -> None:
    out.append("## 2. Play-by-play ile kutu skoru tutarlılığı\n")
    counted = {k: k for k, v in FOUL_KINDS.items() if v not in {"bench", "coach"}}
    defs = {
        "fg2a": sh[sh.value == 2].groupby(PG).size(), "fg2m": sh[(sh.value == 2) & sh.made].groupby(PG).size(),
        "fg3a": sh[sh.value == 3].groupby(PG).size(), "fg3m": sh[(sh.value == 3) & sh.made].groupby(PG).size(),
        "fta": ev[ev.type.isin(["FTM", "FTA"])].groupby(PG).size(), "ftm": ev[ev.type == "FTM"].groupby(PG).size(),
        "orb": ev[ev.type == "O"].groupby(PG).size(), "drb": ev[ev.type == "D"].groupby(PG).size(),
        "ast": ev[ev.type == "AS"].groupby(PG).size(), "stl": ev[ev.type == "ST"].groupby(PG).size(),
        "tov": ev[ev.type == "TO"].groupby(PG).size(), "blk": ev[ev.type == "FV"].groupby(PG).size(),
        "blk_against": ev[ev.type == "AG"].groupby(PG).size(), "fd": ev[ev.type == "RV"].groupby(PG).size(),
        "pf": ev[ev.type.isin(counted)].groupby(PG).size(),
    }
    box = pg.set_index(PG)
    rows, detail = [], []
    for stat, ser in defs.items():
        ser = ser[ser.index.get_level_values("player_id") != ""]
        keys = box.index.union(ser.index)
        a = box[stat].reindex(keys).fillna(0)
        b = ser.reindex(keys).fillna(0)
        bad = a != b
        rows.append({"istatistik": stat, "kutu": int(a.sum()), "olay": int(b.sum()), "farklı_oyuncu_maç": int(bad.sum())})
        for k in keys[bad]:
            detail.append({"season": k[0], "gamecode": k[1], "player_id": k[2], "stat": stat,
                           "box": a[k], "events": b[k]})
    pd.DataFrame(detail).to_csv(AUDIT_DIR / "box_vs_events.csv", index=False)
    out += [table(pd.DataFrame(rows)), ""]

    # final score across sources
    pts = pg.groupby(GAME + ["team"]).pts.sum().rename("box")
    g = pd.concat([games[GAME + ["home", "home_score"]].rename(columns={"home": "team", "home_score": "meta"}),
                   games[GAME + ["away", "away_score"]].rename(columns={"away": "team", "away_score": "meta"})])
    g = g.set_index(GAME + ["team"]).join(pts)
    pp = po.groupby(GAME + ["offense"]).points.sum()
    pp.index.names = GAME + ["team"]
    g = g.join(pp.rename("possessions"))
    last = ev.sort_values(GAME + ["seq"]).groupby(GAME).tail(1).set_index(GAME)[["home_score", "away_score"]]
    out.append("**Skor kaynakları (takım-maç başına):**\n")
    out.append(f"- Kutu skoru ve maç kaydı farklı: {int((g.box != g.meta).sum())} / {len(g)}")
    out.append(f"- Kutu skoru ve hücum tablosu farklı: {int((g.box != g.possessions).sum())} / {len(g)}")
    home = games.set_index(GAME)
    out.append(f"- Son olay skoru ve maç kaydı farklı (maç): "
               f"{int(((last.home_score != home.home_score) | (last.away_score != home.away_score)).sum())} / {len(games)}\n")


def lineup_section(pg, ev, sh, po, st, games, out: list[str]) -> None:
    out.append("## 3. Diziliş, süre ve saat\n")
    out.append(f"- 5 kişi olmayan hücum: {int((~po.lineup_ok).sum())}, şut: {int((~sh.lineup_ok).sum())}")
    out.append(f"- Hücum başlangıcı bitişinden sonra: {int((~po.time_ok).sum())} / {len(po)}")
    e = ev.sort_values(GAME + ["seq"]).copy()
    e["prev"] = e.groupby(GAME).elapsed.shift(1)
    back = e[e.elapsed < e.prev]
    gap = back.prev - back.elapsed
    out.append(f"- Saati geri giden olay: {len(back)} ({back[GAME].drop_duplicates().shape[0]} maç). "
               f"1 sn: {int((gap <= 1).sum())}, 2-5 sn: {int(((gap > 1) & (gap <= 5)).sum())}, >5 sn: {int((gap > 5).sum())}\n")
    wrong = back[gap > 5][GAME + ["period", "seq", "type", "elapsed", "prev"]]
    wrong.to_csv(AUDIT_DIR / "clock_jumps.csv", index=False)

    m = st.groupby(PG).seconds.sum().div(60).rename("stint_min")
    j = pg.set_index(PG).join(m).fillna({"stint_min": 0})
    j["diff"] = j.stint_min - j.minutes
    periods = ev.groupby(GAME).period.max().rename("periods")
    j = j.join(periods, on=GAME)
    j["ot"] = j.periods > 4
    big = j[j["diff"].abs() > 1]
    by = j.groupby("ot").agg(oyuncu_maç=("diff", "size"), fark_1dk_üstü=("diff", lambda d: int((d.abs() > 1).sum())),
                             ort_fark=("diff", "mean")).reset_index().rename(columns={"ot": "uzatmalı"})
    out += ["**Süre farkı (stint - kutu):**\n", table(by), ""]
    team = pg.groupby(GAME + ["team"]).minutes.sum().rename("box_min").reset_index().join(periods, on=GAME)
    team["expected"] = 200 + 25 * (team.periods - 4)
    team["gap"] = team.box_min - team.expected
    tg = team.assign(uzatmalı=team.periods > 4).groupby("uzatmalı").gap.agg(["size", "mean", "min", "max"]).reset_index()
    out += ["**Kutu skorundaki takım dakikası, beklenen süreden fark:**\n", table(tg), ""]
    stint_team = st.groupby(GAME + ["team"]).seconds.sum().div(60).rename("stint_min").reset_index().join(periods, on=GAME)
    stint_team["gap"] = stint_team.stint_min - (200 + 25 * (stint_team.periods - 4))
    sg = stint_team.assign(uzatmalı=stint_team.periods > 4).groupby("uzatmalı").gap.agg(["size", "mean", "min", "max"]).reset_index()
    out += ["**Stint tablosundaki takım dakikası, beklenen süreden fark:**\n", table(sg), ""]
    big.reset_index()[PG + ["team", "player", "minutes", "stint_min", "diff", "periods"]].to_csv(
        AUDIT_DIR / "stint_vs_box.csv", index=False)
    out.append(f"Ayrıntı: `stint_vs_box.csv` ({len(big)} satır, {big.reset_index()[GAME].drop_duplicates().shape[0]} maç).\n")


def flags_section(sh: pd.DataFrame, out: list[str]) -> None:
    out.append("## 4. Temizlik bayrakları (T1-T3)\n")
    rows = [("T1 Umut atışı", sh.is_heave), ("T2 Geçersiz koordinat", ~sh.coord_valid),
            ("T3 Değer-mesafe uyumsuz", ~sh.value_dist_ok)]
    out += [table(pd.DataFrame([{"kural": n, "şut": int(m.sum()), "isabet": round(float(sh[m].made.mean()), 3),
                                 "E2024": int(m[sh.season == "E2024"].sum()), "E2025": int(m[sh.season == "E2025"].sum()),
                                 "E2026": int(m[sh.season == "E2026"].sum())} for n, m in rows])), ""]
    usable = sh[sh.value == 3]
    raw, clean = usable.made.mean(), usable[~usable.is_heave].made.mean()
    out.append(f"T1'in lig üçlük yüzdesine etkisi: %{100 * raw:.2f} yerine %{100 * clean:.2f}.\n")
    per = sh[sh.is_heave].groupby("player_id").size()
    out.append(f"En çok umut atışı kullanan oyuncunun sayısı: {int(per.max())}; bu şutların {int(sh.is_heave.sum())} tanesi {len(per)} oyuncuya dağılıyor.\n")


def coordinate_section(sh: pd.DataFrame, games: pd.DataFrame, out: list[str]) -> None:
    """T4: visiting teams change from game to game but the scorer's table does not, so a
    difference between arenas on visitors' shots cannot come from a team's skill."""
    out.append("## 5. Koordinat yanlılığı testi (T4)\n")
    s = sh[(sh.value == 2) & sh.coord_valid & sh.value_dist_ok].merge(games[GAME + ["home"]], on=GAME)
    s["near"] = s.dist_m <= 0.5
    s["rim"] = s.dist_m <= 1.25
    by_made = s.groupby("made").agg(şut=("near", "size"), ort_mesafe=("dist_m", "mean"), pay_0_5m=("near", "mean"),
                                    pay_1_25m=("rim", "mean")).reset_index()
    out += ["**İsabet ve kaçışların mesafe dağılımı (2 sayılık):**\n", table(by_made), ""]
    bands = pd.cut(s.dist_m, [0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4.25, 7], include_lowest=True)
    b = s.groupby(bands, observed=True).made.agg(["size", "mean"]).reset_index()
    b["dist_m"] = b.dist_m.astype(str)
    out += ["**Mesafeye göre isabet:**\n", table(b), ""]

    pts = s[s.dist_m <= 2].assign(px=lambda d: d.x.round(), py=lambda d: d.y.round())
    conc = []
    for made, g in pts.groupby("made"):
        top = g.groupby(["px", "py"]).size().sort_values(ascending=False)
        conc.append({"isabet": made, "şut": len(g), "farklı_nokta": len(top),
                     "en_sık_10_nokta_payı": round(float(top.head(10).sum() / len(g)), 3)})
    out += ["**Koordinat yığılması (2 m içi):**\n", table(pd.DataFrame(conc)), ""]

    vis = s[s.team != s.home]
    arena = vis.groupby(["season", "home"]).agg(
        şut=("near", "size"), isabet=("made", "mean"),
        isabet_pay_0_5m=("near", lambda n: n[vis.loc[n.index, "made"]].mean()),
        kaçan_pay_0_5m=("near", lambda n: n[~vis.loc[n.index, "made"]].mean()),
        isabet_pay_1_25m=("rim", lambda n: n[vis.loc[n.index, "made"]].mean()),
        kaçan_pay_1_25m=("rim", lambda n: n[~vis.loc[n.index, "made"]].mean())).reset_index()
    arena = arena[arena.şut >= MIN_ARENA_SHOTS]
    arena.to_csv(AUDIT_DIR / "arena_coordinates.csv", index=False)
    arena["fark_0_5m"] = arena.isabet_pay_0_5m - arena.kaçan_pay_0_5m

    def dispersion(rate: pd.Series, n: pd.Series) -> float:
        """Observed between-arena variance over the variance expected from sampling alone."""
        p = float((rate * n).sum() / n.sum())
        return float(((rate - p) ** 2 * n / (p * (1 - p))).sum() / (len(rate) - 1))

    made_n = (vis[vis.made].groupby(["season", "home"]).size().reindex(pd.MultiIndex.from_frame(arena[["season", "home"]]))).to_numpy()
    miss_n = (vis[~vis.made].groupby(["season", "home"]).size().reindex(pd.MultiIndex.from_frame(arena[["season", "home"]]))).to_numpy()
    sm = pd.DataFrame([
        {"ölçüm": "İsabetlerin 0,5 m içi payı", "en_düşük": arena.isabet_pay_0_5m.min(), "medyan": arena.isabet_pay_0_5m.median(),
         "en_yüksek": arena.isabet_pay_0_5m.max(), "yayılım_oranı": dispersion(arena.isabet_pay_0_5m, pd.Series(made_n, arena.index))},
        {"ölçüm": "Kaçanların 0,5 m içi payı", "en_düşük": arena.kaçan_pay_0_5m.min(), "medyan": arena.kaçan_pay_0_5m.median(),
         "en_yüksek": arena.kaçan_pay_0_5m.max(), "yayılım_oranı": dispersion(arena.kaçan_pay_0_5m, pd.Series(miss_n, arena.index))},
        {"ölçüm": "İsabetlerin 1,25 m içi payı", "en_düşük": arena.isabet_pay_1_25m.min(), "medyan": arena.isabet_pay_1_25m.median(),
         "en_yüksek": arena.isabet_pay_1_25m.max(), "yayılım_oranı": dispersion(arena.isabet_pay_1_25m, pd.Series(made_n, arena.index))},
        {"ölçüm": "Kaçanların 1,25 m içi payı", "en_düşük": arena.kaçan_pay_1_25m.min(), "medyan": arena.kaçan_pay_1_25m.median(),
         "en_yüksek": arena.kaçan_pay_1_25m.max(), "yayılım_oranı": dispersion(arena.kaçan_pay_1_25m, pd.Series(miss_n, arena.index))},
        {"ölçüm": "Deplasman 2'lik isabeti", "en_düşük": arena.isabet.min(), "medyan": arena.isabet.median(),
         "en_yüksek": arena.isabet.max(), "yayılım_oranı": dispersion(arena.isabet, arena.şut)},
    ])
    out += [f"**Salonlar arası fark (yalnızca deplasman takımlarının şutları, {len(arena)} salon-sezon):**\n",
            table(sm), "",
            "Yayılım oranı 1'e yakınsa fark örnekleme gürültüsüyle açıklanır. 1'in çok üstü, salonlar arasında gerçek bir "
            "fark olduğunu gösterir. Deplasman takımı her maç değiştiği için bu fark takım becerisinden çok salon/kayıt "
            "farkına işaret eder. Ayrıntı: `arena_coordinates.csv`.\n"]

    # geometry test that does not use make/miss: the arc and the corners are the same in every arena
    geo = sh[sh.coord_valid & ~sh.is_heave].merge(games[GAME + ["home"]], on=GAME)
    rows = []
    for (season, home), d in geo.groupby(["season", "home"]):
        top3 = d[(d.value == 3) & (d.x.abs() <= 150)].y
        close = d[(d.value == 2) & (d.dist_m <= 2.5)].y
        if len(top3) >= 60:
            rows.append({"season": season, "home": home, "arc_y_p05": top3.quantile(.05), "close_y_med": close.median(),
                         "corner_abs_x_med": d[(d.value == 3) & (d.y <= 250)].x.abs().median()})
    arc = pd.DataFrame(rows)
    arc.to_csv(AUDIT_DIR / "arena_geometry.csv", index=False)
    spread = pd.DataFrame([{"ölçüm": n, "en_düşük": arc[c].min(), "medyan": arc[c].median(), "en_yüksek": arc[c].max()}
                           for n, c in (("Üç sayı çizgisi, tepe (y, cm)", "arc_y_p05"),
                                        ("Köşe üçlük |x| (cm)", "corner_abs_x_med"),
                                        ("Yakın şutların medyan y'si (cm)", "close_y_med"))])
    out += [f"**Sonuçtan bağımsız geometri testi ({len(arc)} salon-sezon):**\n", table(spread), "",
            "Çizgiler her salonda yaklaşık aynı yerde, yakın şutların işaretlendiği yer ise çok farklı. Bu nedenle sorun "
            "orijin kayması değil ve tek bir kaydırmayla düzelmez. Ayrıntı: `arena_geometry.csv`.\n"]

    # does the rim-vs-paint split depend on the recording venue more than the combined paint zone does?
    z = sh[(sh.value == 2) & (sh.zone_clean != "unknown")].merge(games[GAME + ["home"]], on=GAME)
    z = z[z.team != z.home]
    rows = []
    for name, zones in (("Pota altı", ["rim"]), ("Boyalı alan (pota altı hariç)", ["paint"]), ("Birleşik pota + boyalı", ["rim", "paint"])):
        d = z[z.zone_clean.isin(zones)].groupby(["season", "home"]).made.agg(["size", "mean"])
        d = d[d["size"] >= MIN_ARENA_SHOTS // 2]
        share = z.assign(inz=z.zone_clean.isin(zones)).groupby(["season", "home"]).inz.agg(["size", "mean"])
        rows.append({"bölge": name, "isabet_en_düşük": d["mean"].min(), "isabet_en_yüksek": d["mean"].max(),
                     "isabet_yayılım": dispersion(d["mean"], d["size"]), "şut_payı_yayılım": dispersion(share["mean"], share["size"])})
    out += ["**Hangi bölge salon farkına daha dayanıklı?**\n", table(pd.DataFrame(rows)), ""]


def rebound_section(rc: pd.DataFrame, out: list[str]) -> None:
    out.append("## 6. Ribaund fırsatları (T6)\n")
    t = rc[rc.team_rebound]
    out.append(f"Toplam ribaund olayı {len(rc)}. Oyuncuya yazılan {int((~rc.team_rebound).sum())}, takım ribaundu {len(t)}.\n")
    prev = t.prev_type.value_counts(normalize=True).head(5).round(3).rename_axis("önceki_olay").reset_index(name="pay")
    nxt = t.next_type.value_counts(normalize=True).head(5).round(3).rename_axis("sonraki_olay").reset_index(name="pay")
    out += ["**Takım ribaundundan önce:**\n", table(prev), "", "**Takım ribaundundan sonra:**\n", table(nxt), ""]
    out.append(f"Ölü olması muhtemel takım ribaundu (`likely_dead`): {int(rc.likely_dead.sum())} / {len(t)}. "
               f"5 kişi olmayan: {int((~rc.lineup_ok).sum())}.\n")


def foul_section(fo: pd.DataFrame, tr: pd.DataFrame, out: list[str]) -> None:
    out.append("## 7. Faul ve serbest atış serileri\n")
    k = fo.groupby("foul_kind").agg(adet=("seq", "size"), faul_alan_bağlı=("drawn_by", lambda d: round(float((d != "").mean()), 3))).reset_index()
    out += [table(k), ""]
    of = fo[fo.foul_kind == "offensive"]
    out.append(f"Hücum faulünde faulü alan savunmacı bağlandı: {int((of.drawn_by != '').sum())} / {len(of)}. "
               "Veri charge ile perde faulü gibi türleri ayırmıyor.\n")
    t = tr.groupby("kind").agg(seri=("shots", "size"), atış=("shots", "sum"), isabet=("made", "sum")).reset_index()
    t["pay"] = (t.seri / t.seri.sum()).round(3)
    out += [table(t), ""]
    out.append(f"Toplam atış {int(tr.shots.sum())}. `shooting_or_penalty` serileri şut faulü de bonus da olabilir ve "
               "faul alınan şutun koordinatı kayıtlı değildir.\n")


def block_section(sh: pd.DataFrame, ev: pd.DataFrame, out: list[str]) -> None:
    out.append("## 8. Blok bağlantısı\n")
    ag, fv = int((ev.type == "AG").sum()), int((ev.type == "FV").sum())
    linked = int(sh.blocked.sum())
    has = int((sh.blocker_id != "").sum())
    out.append(f"`AG` {ag}, `FV` {fv}. Şuta bağlanan `AG`: {linked} (%{100 * linked / ag:.1f}). "
               f"Bloklayana da bağlanan: {has} (%{100 * has / fv:.1f} / FV).\n")
    b = sh[sh.blocked].groupby(sh.value).size().to_dict()
    z = sh[sh.blocked].zone_clean.value_counts().to_dict()
    out.append(f"Değere göre: {b}. Bölgeye göre: {z}.\n")


def people_section(pg: pd.DataFrame, pe: pd.DataFrame, out: list[str]) -> None:
    out.append("## 9. Boy, kilo, pozisyon\n")
    if pe.empty:
        out.append("Veri yok.\n")
        return
    j = pg.merge(pe[["season", "player_id", "height", "weight", "position"]], on=["season", "player_id"], how="left")
    rows = []
    for season, g in j.groupby("season"):
        rows.append({"sezon": season, "dakika_payı_boy": round(float(g[g.height.notna()].minutes.sum() / g.minutes.sum()), 4),
                     "dakika_payı_pozisyon": round(float(g[g.position.notna()].minutes.sum() / g.minutes.sum()), 4),
                     "boysuz_oyuncu": int(g[g.height.isna()].player_id.nunique()),
                     "pozisyonsuz_oyuncu": int(g[g.position.isna()].player_id.nunique())})
    out += [table(pd.DataFrame(rows)), ""]
    h = pe.dropna(subset=["height"])
    out.append(f"Boy aralığı {int(h.height.min())}-{int(h.height.max())} cm. Pozisyon ortalama boy: "
               f"{h.groupby('position').height.mean().round(1).to_dict()}.\n")
    drift = pe.groupby("player_id").agg(hmin=("height", "min"), hmax=("height", "max"), pos=("position", "nunique"))
    out.append(f"Sezonlar arasında boyu 2 cm'den fazla değişen oyuncu: {int((drift.hmax - drift.hmin > 2).sum())}. "
               f"Pozisyonu değişen oyuncu: {int((drift.pos > 1).sum())}.\n")


def main() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    read = lambda n: pd.read_parquet(TABLES_DIR / f"{n}.parquet")  # noqa: E731
    pg, ev, sh, po, st, games = map(read, ["player_games", "events", "shots", "possessions", "stints", "games"])
    rc, fo, tr, pe, off = map(read, ["rebound_chances", "fouls", "ft_trips", "people", "official_totals"])
    out = ["# Aşama 1: Veri temeli denetimi\n",
           f"{len(games)} maç, {len(pg):,} oyuncu-maç, {len(ev):,} olay, {len(sh):,} şut.\n"]
    official_section(pg, off, out)
    internal_section(pg, ev, sh, po, games, out)
    lineup_section(pg, ev, sh, po, st, games, out)
    flags_section(sh, out)
    coordinate_section(sh, games, out)
    rebound_section(rc, out)
    foul_section(fo, tr, out)
    block_section(sh, ev, out)
    people_section(pg, pe, out)
    text = "\n".join(out)
    (AUDIT_DIR / "foundation.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
