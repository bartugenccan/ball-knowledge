"""The games we got badly wrong, one by one: what happened, and could it have been seen coming?

    uv run python scripts/match/misses.py

Reads the scorecard (scripts/match/scorecard.py), simulates nothing. For each big miss it splits the
gap into shot making, shot volume and free throws, sizes the shot making against chance, and names
the players who moved the result. Then the question that matters: was there a sign before tip-off?

Writes data/audit/match_misses.md and data/audit/match_misses.json.
"""

from __future__ import annotations

import json
import math
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from bk.config import AUDIT_DIR  # noqa: E402
from bk.match.narrate import short_name  # noqa: E402

ENRICHED = AUDIT_DIR / "match_scorecard_enriched.parquet"
PLAYERS = AUDIT_DIR / "match_scorecard_players.parquet"
BIG_MISS = 20.0             # points of error on the margin
CONFIDENT = 0.65            # a wrong favorite this sure counts as a miss too
CHANCE_Z = 1.5              # below this, the shooting gap is an ordinary night
TEAM_NIGHT_Z = 2.0          # one side's shooting this far off makes it an unusual night by itself
MINUTES_SHOCK = 10.0        # minutes away from what was expected
RESIDUAL_PRIOR_GAMES = 8.0  # how many games a team's past error is pulled toward zero by
LABELS = {"chance": "Şans: şut isabeti olağan sapmada", "hot_night": "Olağan dışı şut gecesi", "volume": "Hücum ve şut hacmi", "free_throws": "Serbest atış", "players": "Dakikası sapan oyuncular"}


def components(g: pd.DataFrame) -> pd.DataFrame:
    """The margin error split into parts, all from the home side's point of view. They add up exactly."""
    out = pd.DataFrame(index=g.index)
    chance = 0.0
    for name in ("h", "a"):
        p2 = g[f"{name}_f2m_sim"] / g[f"{name}_f2a_sim"].clip(lower=1)
        p3 = g[f"{name}_f3m_sim"] / g[f"{name}_f3a_sim"].clip(lower=1)
        a2, a3 = g[f"{name}_f2a_real"], g[f"{name}_f3a_real"]
        out[f"{name}_three_acc"] = 3 * (g[f"{name}_f3m_real"] - a3 * p3)
        out[f"{name}_two_acc"] = 2 * (g[f"{name}_f2m_real"] - a2 * p2)
        out[f"{name}_three_vol"] = 3 * (a3 - g[f"{name}_f3a_sim"]) * p3
        out[f"{name}_two_vol"] = 2 * (a2 - g[f"{name}_f2a_sim"]) * p2
        out[f"{name}_ft"] = g[f"{name}_ftm_real"] - g[f"{name}_ftm_sim"]
        out[f"{name}_three_z"] = (g[f"{name}_f3m_real"] - a3 * p3) / np.sqrt((a3 * p3 * (1 - p3)).clip(lower=1e-6))
        out[f"{name}_two_z"] = (g[f"{name}_f2m_real"] - a2 * p2) / np.sqrt((a2 * p2 * (1 - p2)).clip(lower=1e-6))
        out[f"{name}_three_pct_real"] = 100 * g[f"{name}_f3m_real"] / a3.clip(lower=1)
        out[f"{name}_three_pct_sim"] = 100 * p3
        out[f"{name}_two_pct_real"] = 100 * g[f"{name}_f2m_real"] / a2.clip(lower=1)
        out[f"{name}_two_pct_sim"] = 100 * p2
        chance = chance + 9 * a3 * p3 * (1 - p3) + 4 * a2 * p2 * (1 - p2)
    out["accuracy"] = out.h_three_acc + out.h_two_acc - out.a_three_acc - out.a_two_acc
    out["volume"] = out.h_three_vol + out.h_two_vol - out.a_three_vol - out.a_two_vol
    out["free_throws"] = out.h_ft - out.a_ft
    out["error"] = (g.h_pts_real - g.a_pts_real) - (g.h_pts_sim - g.a_pts_sim)
    out["accuracy_z"] = out.accuracy / np.sqrt(chance.clip(lower=1e-6))
    return out


def player_shocks(pl: pd.DataFrame) -> dict[tuple[str, int], dict]:
    """Per game: who moved the result most, and who played far from the expected minutes."""
    out: dict[tuple[str, int], dict] = {}
    for key, part in pl.groupby(["season", "gamecode"]):
        p = part.assign(pts_gap=part.pts_real - part.pts_sim, min_gap=(part.sec_real - part.sec_sim) / 60)
        top = p.reindex(p.pts_gap.abs().sort_values(ascending=False).index).head(4)
        shock = p[(p.min_gap.abs() >= MINUTES_SHOCK) & ((p.sec_sim / 60 >= 15) | (p.sec_real / 60 >= 15))]
        # what those players' points did to the home side's margin, against what was expected of them
        home_effect = float(sum((r.pts_real - r.pts_sim) * (1 if r.side == 0 else -1) for r in shock.itertuples()))
        fouled = p[p.pf_real >= 5]
        out[key] = {
            "players": [{"team": r.team, "name": short_name(r.player), "pts": int(r.pts_real), "expected": round(r.pts_sim, 1), "min": round(r.sec_real / 60), "expected_min": round(r.sec_sim / 60)} for r in top.itertuples()],
            "minutes": [{"team": r.team, "name": short_name(r.player), "min": round(r.sec_real / 60), "expected_min": round(r.sec_sim / 60), "points_lost": round(r.pts_sim * r.min_gap / max(r.sec_sim / 60, 1), 1)} for r in shock.itertuples()],
            "fouled_out": [short_name(r.player) for r in fouled.itertuples()],
            "minutes_shock_points": float(sum(abs(r.pts_sim * r.min_gap / max(r.sec_sim / 60, 1)) for r in shock.itertuples())),
            "minutes_effect": home_effect,
            "new_minutes": float(p[p.games_before == 0].sec_real.sum() / 60),
        }
    return out


def label(row, shock: dict) -> str:
    """What mostly made this game different. The parts are compared in the direction of the error."""
    sign = np.sign(row.error) or 1.0
    parts = {"accuracy": sign * row.accuracy, "volume": sign * row.volume, "free_throws": sign * row.free_throws}
    main = max(parts, key=parts.get)
    if sign * shock["minutes_effect"] >= 0.5 * abs(row.error):
        return "players"
    if main == "accuracy":
        team_z = max(abs(row.h_three_z), abs(row.h_two_z), abs(row.a_three_z), abs(row.a_two_z))
        return "hot_night" if abs(row.accuracy_z) >= CHANCE_Z or team_z >= TEAM_NIGHT_Z else "chance"
    return main


def past_residuals(g: pd.DataFrame) -> pd.DataFrame:
    """Before each game: how far the model had been off on each team's scoring and defending this season.

    Pulled toward zero, since a few games of error are mostly chance.
    """
    rows = []
    for name, team, opp_name in (("h", "home", "a"), ("a", "away", "h")):
        rows.append(pd.DataFrame({"season": g.season, "gamecode": g.gamecode, "date": g.date, "team": g[team], "side": name,
                                  "off": g[f"{name}_pts_real"] - g[f"{name}_pts_sim"], "dfn": g[f"{opp_name}_pts_real"] - g[f"{opp_name}_pts_sim"]}))
    long = pd.concat(rows, ignore_index=True).sort_values("date")
    for col in ("off", "dfn"):
        sums = long.groupby(["season", "team"])[col].transform(lambda v: v.shift().fillna(0).cumsum())
        counts = long.groupby(["season", "team"])[col].transform(lambda v: np.arange(len(v), dtype=float))
        long[f"past_{col}"] = sums / (counts + RESIDUAL_PRIOR_GAMES)
    wide = long.pivot(index=["season", "gamecode"], columns="side", values=["past_off", "past_dfn"])
    # what the past says about tonight's margin: my scoring and yours, each with both teams' record
    signal = (wide["past_off"]["h"] + wide["past_dfn"]["a"]) - (wide["past_off"]["a"] + wide["past_dfn"]["h"])
    return signal.rename("past_signal").reset_index()


def pct(x: float) -> str:
    return f"%{x:.0f}"


def sentence(r, c, shock: dict) -> str:
    """One plain account of a miss, from the parts that pushed it hardest."""
    home, away = r.home, r.away
    parts = []
    named = (("h", home), ("a", away))
    for name, team in named:
        for kind, label_, z_col, real, sim in (("three_acc", "üçlük", "three_z", "three_pct_real", "three_pct_sim"), ("two_acc", "ikilik", "two_z", "two_pct_real", "two_pct_sim")):
            points = c[f"{name}_{kind}"]
            pushes = (1 if name == "h" else -1) * points * np.sign(c["error"])
            if pushes >= 5:
                unusual = " (olağan dışı)" if abs(c[f"{name}_{z_col}"]) >= 2 else ""
                parts.append((pushes, f"{team} {label_} {pct(c[f'{name}_{real}'])}, beklenen {pct(c[f'{name}_{sim}'])}: {points:+.0f} sayı{unusual}"))
        for kind, label_ in (("three_vol", "üçlük sayısı"), ("two_vol", "ikilik sayısı"), ("ft", "serbest atış")):
            points = c[f"{name}_{kind}"]
            pushes = (1 if name == "h" else -1) * points * np.sign(c["error"])
            if pushes >= 5:
                parts.append((pushes, f"{team} {label_}: {points:+.0f} sayı"))
    parts.sort(key=lambda p: -p[0])
    text = "; ".join(p[1] for p in parts[:4]) or "Tek bir bileşen öne çıkmıyor"
    extra = []
    if shock["minutes"]:
        extra.append("Dakika sapması: " + ", ".join(f"{m['name']} {m['min']} dk (beklenen {m['expected_min']})" for m in shock["minutes"][:3]))
    if shock["fouled_out"]:
        extra.append("5 faul: " + ", ".join(shock["fouled_out"][:3]))
    return text + (". " + ". ".join(extra) if extra else "")


def table(rows: list[list], header: list[str]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def main() -> None:
    g = pd.read_parquet(ENRICHED).sort_values("date").reset_index(drop=True)
    pl = pd.read_parquet(PLAYERS)
    c = components(g)
    shocks = player_shocks(pl)
    g = g.merge(past_residuals(g), on=["season", "gamecode"], how="left")
    g["sim_margin"] = g.h_pts_sim - g.a_pts_sim
    g["real_margin"] = g.h_pts_real - g.a_pts_real
    g["wrong_favorite"] = ((g.p_home >= CONFIDENT) & ~g.home_won) | ((g.p_home <= 1 - CONFIDENT) & g.home_won)
    g["big"] = c.error.abs() >= BIG_MISS
    g["miss"] = g.big | g.wrong_favorite
    # what net rating would have said, in points, fitted on the season before where one exists
    fit = g[g.season == "E2025"]
    slope, intercept = np.polyfit(fit.net_gap, fit.real_margin, 1)
    g["net_margin"] = intercept + slope * g.net_gap

    records = []
    for i, r in g.iterrows():
        shock = shocks[(r.season, int(r.gamecode))]
        records.append({"season": r.season, "gamecode": int(r.gamecode), "round": int(r["round"]), "phase": r.phase, "home": r.home, "away": r.away,
                        "sim": [round(r.h_pts_sim), round(r.a_pts_sim)], "real": [int(r.h_pts_real), int(r.a_pts_real)], "error": round(float(c.error[i]), 1),
                        "accuracy": round(float(c.accuracy[i]), 1), "volume": round(float(c.volume[i]), 1), "free_throws": round(float(c.free_throws[i]), 1),
                        "accuracy_z": round(float(c.accuracy_z[i]), 2), "label": label(c.loc[i], shock), "story": sentence(r, c.loc[i], shock),
                        "net_margin": round(float(r.net_margin), 1), "sim_margin": round(float(r.sim_margin), 1), "past_signal": None if pd.isna(r.past_signal) else round(float(r.past_signal), 1),
                        "big": bool(r.big), "wrong_favorite": bool(r.wrong_favorite), "players": shock["players"], "minutes": shock["minutes"], "fouled_out": shock["fouled_out"]})
    (AUDIT_DIR / "match_misses.json").write_text(json.dumps(records, ensure_ascii=False, indent=0), encoding="utf-8")
    d = pd.DataFrame(records)
    misses = d[d.big | d.wrong_favorite]
    big = d[d.big]

    lines = ["# Büyük ıskalar", "", f"{len(g)} maçın {int(d.big.sum())} tanesinde skor farkı hatası en az {BIG_MISS:.0f} sayı. {int(d.wrong_favorite.sum())} maçta en az %{100 * CONFIDENT:.0f} güvenle yanlış takımı favori gösterdik. Birleşimi {len(misses)} maç.", ""]

    # how much can chance alone produce?
    expected = 1 - math.erf(BIG_MISS / g.margin_sd.mean() / math.sqrt(2))
    lines += ["## Bu kadar ıska normal mi?", "", f"Modelin kendi dağılımına göre, tamamen doğru bir modelde bile maçların yaklaşık %{100 * expected:.0f}'si {BIG_MISS:.0f}+ sayı ıskalanırdı (beklenen dağılım SD {g.margin_sd.mean():.1f}). Gerçekte %{100 * d.big.mean():.0f}. Yani büyük ıskaların çoğu tek başına modelin hatası sayılamaz; ama hangilerinin öyle olduğunu ayırmak gerekiyor.", ""]

    rows = []
    for key, text in LABELS.items():
        part = big[big.label == key]
        rows.append([text, len(part), f"{len(part) / max(len(big), 1):.0%}", f"{part.error.abs().mean():.1f}" if len(part) else "-"])
    lines += ["## Büyük ıskaların ana nedeni", ""] + table(rows, ["Neden", "Maç", "Pay", "Ortalama ıska"]) + [""]

    # big misses against ordinary games
    x = g.assign(acc=c.accuracy.abs(), vol=c.volume.abs(), ft=c.free_throws.abs(), err=c.error.abs(),
                 poss_gap=(g.h_poss_real - g.h_poss_sim).abs() + (g.a_poss_real - g.a_poss_sim).abs(),
                 tov_gap=((g.h_tov_real - g.h_tov_sim) - (g.a_tov_real - g.a_tov_sim)).abs(),
                 orb_gap=((g.h_orb_real - g.h_orb_sim) - (g.a_orb_real - g.a_orb_sim)).abs(),
                 shock=[shocks[(s, int(k))]["minutes_shock_points"] for s, k in zip(g.season, g.gamecode)],
                 new=[shocks[(s, int(k))]["new_minutes"] for s, k in zip(g.season, g.gamecode)],
                 fouled=[len(shocks[(s, int(k))]["fouled_out"]) for s, k in zip(g.season, g.gamecode)],
                 early=(g.phase == "RS") & (g["round"] <= 5), net_closer=(g.net_margin - g.real_margin).abs() < (g.sim_margin - g.real_margin).abs())
    rows = []
    for col, text, fmt in (("acc", "Şut isabeti sapması (sayı)", "{:.1f}"), ("vol", "Şut hacmi sapması (sayı)", "{:.1f}"), ("ft", "Serbest atış sapması (sayı)", "{:.1f}"), ("poss_gap", "Hücum sayısı sapması", "{:.1f}"),
                           ("tov_gap", "Top kaybı farkı sapması", "{:.1f}"), ("orb_gap", "Hücum ribaundu farkı sapması", "{:.1f}"), ("shock", "Dakika şoku (sayı karşılığı)", "{:.1f}"), ("fouled", "5 faulle çıkan oyuncu", "{:.2f}"),
                           ("new", "Yeni oyuncu dakikası", "{:.1f}"), ("early", "İlk 5 hafta payı", "{:.0%}"), ("overtime_real", "Uzatma payı", "{:.0%}"), ("net_closer", "Net reyting gerçeğe daha yakın", "{:.0%}")):
        a, b = x[x.big][col].astype(float).mean(), x[~x.big][col].astype(float).mean()
        rows.append([text, fmt.format(a), fmt.format(b)])
    lines += ["## Büyük ıskalar diğer maçlardan neyle ayrılıyor?", ""] + table(rows, ["Ölçüm", f"Büyük ıska ({int(x.big.sum())} maç)", f"Diğerleri ({int((~x.big).sum())} maç)"]) + [""]

    # were there signs before tip-off?
    lines += ["## Maçtan önce işaret var mıydı?", "", "Hata, maçtan önce bilinen bir şeyle öngörülebiliyorsa düzeltilebilir demektir. Eğim E2025'te bulundu, sonra E2026'ya uygulandı: E2026 satırındaki iyileşme ayardan bağımsızdır.", ""]
    rows = []
    signals = {"Net reytingin simülasyondan farkı": (g.net_margin - g.sim_margin), "Modelin bu takımlardaki geçmiş hatası": g.past_signal}
    train = (g.season == "E2025").to_numpy()
    test = (g.season == "E2026").to_numpy()
    err = c.error.to_numpy()
    for name, sig in signals.items():
        s = sig.fillna(0).to_numpy()
        beta = float((s[train] * err[train]).sum() / (s[train] ** 2).sum())
        se = float(np.sqrt(((err[train] - beta * s[train]) ** 2).mean() / (s[train] ** 2).sum()))
        before, after = np.mean(np.abs(err[test])), np.mean(np.abs(err[test] - beta * s[test]))
        rmse_before, rmse_after = np.sqrt(np.mean(err[test] ** 2)), np.sqrt(np.mean((err[test] - beta * s[test]) ** 2))
        big_share = float(np.mean(np.sign(s[np.abs(err) >= BIG_MISS]) == np.sign(err[np.abs(err) >= BIG_MISS])))
        rows.append([name, f"{beta:.2f} ({se:.2f})", f"{np.corrcoef(s[train], err[train])[0, 1]:+.3f}", f"{np.corrcoef(s[test], err[test])[0, 1]:+.3f}", f"{rmse_before:.2f} → {rmse_after:.2f}", f"{before:.2f} → {after:.2f}", f"{big_share:.0%}"])
    lines += table(rows, ["İşaret", "Eğim (SE)", "Korelasyon E2025", "Korelasyon E2026", "E2026 RMSE", "E2026 hata", "Büyük ıskalarda doğru yön"]) + [""]

    # teams
    team = pd.concat([d.assign(team=d.home, e=d.error), d.assign(team=d.away, e=-d.error)])
    team["key"] = team.season + " " + team.team
    tm = team.groupby("key").agg(games=("e", "size"), mean=("e", "mean"), big=("big", "sum")).query("games >= 8").sort_values("mean")
    rows = [[k, int(v.games), f"{v['mean']:+.1f}", int(v.big)] for k, v in pd.concat([tm.head(5), tm.tail(5)]).iterrows()]
    lines += ["## Takımlar", "", "Ortalama: takımın gerçek skor farkı eksi beklenen. Artı: modelin hafife aldığı.", ""] + table(rows, ["Takım", "Maç", "Ortalama", "Büyük ıska"]) + [""]

    lines += ["## Maç maç", "", f"En büyük {min(40, len(big))} ıska. Hepsi `match_misses.json` içinde.", ""]
    rows = []
    for r in big.reindex(big.error.abs().sort_values(ascending=False).index).head(40).itertuples():
        rows.append([f"{r.season} H{r.round} {r.home}-{r.away}", f"{r.sim[0]}-{r.sim[1]}", f"{r.real[0]}-{r.real[1]}", f"{r.error:+.0f}", LABELS[r.label].split(":")[0], r.story])
    lines += table(rows, ["Maç", "Beklenen", "Gerçek", "Iska", "Neden", "Ne oldu"])
    out = "\n".join(lines) + "\n"
    (AUDIT_DIR / "match_misses.md").write_text(out, encoding="utf-8")
    print(out.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
