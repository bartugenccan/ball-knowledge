"""How a team plays, measured from the play-by-play and tied to its players.

    uv run python -m bk.team.style

Each tendency is a count over a clear opportunity, compared with the rest of the league. A tendency
only earns a sentence if it holds up: the first ten games of a season must predict the rest
(scripts/audit/team_style_reliability.py). The public feed has no play types, so this page says what
a team does, not how it draws it up: "takes 45% of its shots from three", not "runs a lot of pick and roll".
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from bk.config import AUDIT_DIR, TABLES_DIR
from bk.match.calibrate import MINUTES
from bk.match.narrate import short_name
from bk.ratings.metrics_v2 import Tables, display_value, load_tables

STYLE_FILE = TABLES_DIR / "team_style.json"
RELIABILITY_FILE = AUDIT_DIR / "team_style_reliability.json"
MIN_STABILITY = 0.60        # first ten games against the rest
EARLY_SEASON_GAMES = 10
ROTATION_PLAYERS = 11
ZONES = ("inside", "mid", "corner3", "above_break3")


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    group: str
    num: str
    den: str
    scale: float = 100.0
    unit: str = "%"
    digits: int = 1
    high: str = ""      # how a high value reads
    low: str = ""       # how a low value reads
    hint: str = ""


GROUPS = {"tempo": "Tempo", "shots": "Şut tercihi", "creation": "Şutu kim yaratıyor", "glass": "Ribaund ve faul", "defense": "Savunma", "rotation": "Rotasyon"}

METRICS: tuple[Metric, ...] = (
    Metric("poss_len", "Hücum süresi", "tempo", "poss_seconds", "poss_counted", 1, " sn", 1, "yavaş ve sabırlı hücum eden", "hızlı hücum bitiren",
           "Topu alıp hücumu bitirene kadar geçen ortalama süre. Hücum ribaundu sonrası devam eden süre dahildir."),
    Metric("transition", "Geçiş hücumu payı", "tempo", "trans_shots", "first_shots", 100, "%", 1, "geçişe çok koşan", "geçişe az çıkan",
           "Topu aldıktan sonraki ilk 7 saniyede atılan şutların payı."),
    Metric("early", "Erken şut payı", "tempo", "early_shots", "hc_shots", 100, "%", 1, "set hücumunda erken şut arayan", "set hücumunda saati sonuna kadar kullanan",
           "Yerleşik hücumda ilk 10 saniyede atılan şutların payı."),
    Metric("three_share", "Üçlük payı", "shots", "threes", "shots", 100, "%", 1, "üçlüğe yaslanan", "üçlükten uzak duran", "Tüm şutlar içinde üçlüklerin payı."),
    Metric("inside_share", "Boyalı alan payı", "shots", "insides", "shots", 100, "%", 1, "potaya yüklenen", "potaya az giden", "Tüm şutlar içinde boyalı alan şutlarının payı."),
    Metric("mid_share", "Orta mesafe payı", "shots", "mids", "shots", 100, "%", 1, "orta mesafeyi çok kullanan", "orta mesafeyi neredeyse hiç kullanmayan",
           "Tüm şutlar içinde orta mesafe şutlarının payı."),
    Metric("corner_share", "Köşe üçlüğü payı", "shots", "corners", "threes", 100, "%", 1, "üçlüğü köşeden arayan", "üçlüğü köşe dışından arayan", "Üçlükler içinde köşe üçlüklerinin payı."),
    Metric("assisted", "Asistli sayı payı", "creation", "assisted", "makes", 100, "%", 1, "şutu pasla yaratan", "şutu bireysel yaratan", "Giren şutlar içinde asistli olanların payı."),
    Metric("top3_usage", "İlk 3 oyuncunun top kullanımı", "creation", "top3_touch", "touches", 100, "%", 1, "hücumu birkaç oyuncuya emanet eden", "hücumu geniş bir kadroya yayan",
           "Maç başına en çok top kullanan üç oyuncunun şut, serbest atış, asist ve top kaybı payı."),
    Metric("orb", "Hücum ribaundu", "glass", "orb", "orb_chances", 100, "%", 1, "hücum ribaunduna giden", "savunmaya geri dönmeyi seçen", "Kaçan şutlardan alınan hücum ribaundu payı."),
    Metric("drb", "Savunma ribaundu", "glass", "drb", "drb_chances", 100, "%", 1, "savunma ribaundunu kapatan", "savunma ribaundunda zorlanan", "Rakibin kaçırdığı şutlardan alınan ribaund payı."),
    Metric("ftr", "Çizgiye gitme", "glass", "fta", "shots", 100, "%", 1, "faul alarak oynayan", "çizgiye az giden", "Serbest atış denemesi / şut denemesi."),
    Metric("turnovers", "Top kaybı", "glass", "tov", "poss", 100, "%", 1, "topu çok kaybeden", "topu koruyan", "Hücum başına top kaybı."),
    Metric("opp_three", "Rakibe bırakılan üçlük", "defense", "opp_threes", "opp_shots", 100, "%", 1, "rakibi üçlüğe iten", "üçlüğü kapatan", "Rakibin şutları içinde üçlük payı."),
    Metric("opp_inside", "Rakibe bırakılan boyalı alan", "defense", "opp_insides", "opp_shots", 100, "%", 1, "boyalıya girişe izin veren", "boyalıyı kapatan", "Rakibin şutları içinde boyalı alan payı."),
    Metric("opp_tov", "Rakibe yaptırılan top kaybı", "defense", "opp_tov", "opp_poss", 100, "%", 1, "top kaybı zorlayan", "top kaybı zorlamayan", "Rakip hücumların top kaybıyla bitme payı."),
    Metric("opp_ftr", "Rakibi çizgiye gönderme", "defense", "opp_fta", "opp_shots", 100, "%", 1, "çok faul yapan", "faulsüz savunan", "Rakibin serbest atış denemesi / şut denemesi."),
    Metric("depth", "Rotasyon derinliği", "rotation", "ten_min", "games", 1, " oyuncu", 1, "geniş rotasyonla oynayan", "dar rotasyonla oynayan", "Maç başına en az 10 dakika alan oyuncu sayısı."),
    Metric("top5_minutes", "İlk 5 oyuncunun dakika payı", "rotation", "top5_min", "all_min", 100, "%", 1, "ilk beşe yaslanan", "dakikayı yayan", "Maç başına en çok süre alan beş oyuncunun dakika payı."),
)
BY_KEY = {m.key: m for m in METRICS}


def team_game_counts(t: Tables) -> pd.DataFrame:
    """Counts per team per game. Every metric above is a ratio of two of these columns."""
    keys = ["season", "gamecode", "team"]
    s = t.shots[t.shots.zone_group.isin(ZONES)].copy()
    first = s.since_orb.isna()
    hc = s.context == "halfcourt"
    s["shots"] = 1
    s["threes"] = (s.value == 3).astype(int)
    s["insides"] = (s.zone_group == "inside").astype(int)
    s["mids"] = (s.zone_group == "mid").astype(int)
    s["corners"] = (s.zone_group == "corner3").astype(int)
    s["makes"] = s.made.astype(int)
    s["assisted"] = (s.made & s.assisted).astype(int)
    s["trans_shots"] = (first & (s.context == "transition")).astype(int)
    s["first_shots"] = first.astype(int)
    s["hc_shots"] = (first & hc).astype(int)
    s["early_shots"] = (first & hc & (s.poss_seconds <= 10)).astype(int)
    cols = ["shots", "threes", "insides", "mids", "corners", "makes", "assisted", "trans_shots", "first_shots", "hc_shots", "early_shots"]
    own = s.groupby(keys)[cols].sum()

    opp = s.groupby(["season", "gamecode", "opponent"])[["shots", "threes", "insides"]].sum()
    opp.index.names = keys
    opp.columns = ["opp_shots", "opp_threes", "opp_insides"]

    po = t.possessions[t.possessions.time_ok].copy()
    po["L"] = (po.end - po.start).clip(0, 60)
    offense = po.groupby(["season", "gamecode", "offense"]).agg(poss=("points", "size"), poss_seconds=("L", "sum"), points=("points", "sum"))
    offense.index.names = keys
    offense["poss_counted"] = offense.poss
    defense = po.groupby(["season", "gamecode", "defense"]).agg(opp_poss=("points", "size"), opp_points=("points", "sum"))
    defense.index.names = keys

    pg = t.player_games.copy()
    pg["touch"] = pg.fg2a + pg.fg3a + 0.44 * pg.fta + pg.tov + pg.ast
    box = pg.groupby(keys).agg(fta=("fta", "sum"), tov=("tov", "sum"), orb=("orb", "sum"), drb=("drb", "sum"), all_min=("minutes", "sum"), touches=("touch", "sum"))
    box["games"] = 1
    top3 = pg.sort_values("touch", ascending=False).groupby(keys).touch.apply(lambda v: v.head(3).sum()).rename("top3_touch")
    top5 = pg.sort_values("minutes", ascending=False).groupby(keys).minutes.apply(lambda v: v.head(5).sum()).rename("top5_min")
    ten = pg[pg.minutes >= 10].groupby(keys).size().rename("ten_min")

    out = own.join(opp).join(offense).join(defense).join(box).join(top3).join(top5).join(ten).fillna(0.0).reset_index()
    games = out[["season", "gamecode", "team"]].merge(out, on=["season", "gamecode"], suffixes=("", "_o"))
    games = games[games.team != games.team_o]
    pair = games[["season", "gamecode", "team", "team_o"]]
    other = out.set_index(keys)[["fta", "tov", "orb", "drb"]].add_prefix("o_")
    merged = out.merge(pair, on=["season", "gamecode", "team"]).join(other, on=["season", "gamecode", "team_o"])
    merged["opp_fta"] = merged.o_fta
    merged["opp_tov"] = merged.o_tov
    merged["orb_chances"] = merged.orb + merged.o_drb
    merged["drb_chances"] = merged.drb + merged.o_orb
    return merged


def rate(frame: pd.DataFrame, m: Metric) -> pd.Series:
    return m.scale * frame[m.num] / frame[m.den].where(frame[m.den] > 0)


def stability(counts: pd.DataFrame, seasons: tuple[str, ...] = ("E2024", "E2025")) -> dict[str, dict[str, float]]:
    """How well a team's first ten games predict its other games, and one half of its games the other half."""
    out: dict[str, dict[str, float]] = {}
    for m in METRICS:
        first, halves = [], []
        for season in seasons:
            d = counts[counts.season == season].sort_values("gamecode").copy()
            d["i"] = d.groupby("team").cumcount()
            a = d[d.i < EARLY_SEASON_GAMES].groupby("team")[[m.num, m.den]].sum()
            b = d[d.i >= EARLY_SEASON_GAMES].groupby("team")[[m.num, m.den]].sum()
            first.append(float(rate(a, m).corr(rate(b, m))))
            c = d[d.i % 2 == 0].groupby("team")[[m.num, m.den]].sum()
            e = d[d.i % 2 == 1].groupby("team")[[m.num, m.den]].sum()
            halves.append(float(rate(c, m).corr(rate(e, m))))
        out[m.key] = {"first_ten_vs_rest": round(float(np.mean(first)), 3), "split_half": round(float(np.mean(halves)), 3)}
    return out


def load_stability() -> dict[str, dict[str, float]]:
    if RELIABILITY_FILE.exists():
        return json.loads(RELIABILITY_FILE.read_text(encoding="utf-8"))
    return {}


def rotation_table(t: Tables, season: str, team: str, names: dict[str, str]) -> list[dict]:
    """Who plays in which minute: the share of his games a player is on court, minute by minute."""
    s = t.stints[(t.stints.season == season) & (t.stints.team == team) & (t.stints.start < MINUTES * 60)]
    pg = t.player_games[(t.player_games.season == season) & (t.player_games.team == team) & (t.player_games.minutes > 0)]
    games = pg.groupby("player_id").agg(games=("gamecode", "nunique"), minutes=("minutes", "sum"), starts=("starter", "sum"))
    team_games = pg.gamecode.nunique()
    out = []
    for pid, row in games.sort_values("minutes", ascending=False).head(ROTATION_PLAYERS).iterrows():
        seconds = np.zeros(MINUTES)
        for a, b in zip(s[s.player_id == pid].start.to_numpy(), s[s.player_id == pid].end.to_numpy()):
            for m in range(int(a // 60), int(min(b, MINUTES * 60 - 1) // 60) + 1):
                seconds[m] += max(0.0, min(b, (m + 1) * 60) - max(a, m * 60))
        out.append({"player_id": str(pid), "name": short_name(names.get(pid, pid)), "mpg": round(float(row.minutes / row.games), 1), "games": int(row.games),
                    "starts": int(row.starts), "of_games": int(team_games),
                    "curve": [round(float(x), 2) for x in seconds / (60 * row.games)]})
    return out


def _carriers(ratings: pd.DataFrame, pm: pd.DataFrame, metric: str) -> list[dict]:
    """The players behind a tendency: who has the most of it and what their ratings say."""
    picks = {
        "three_share": ("three_rate", "three_point"), "corner_share": ("three_rate", "three_point"),
        "inside_share": ("inside_rate", "finishing"), "mid_share": ("mid_rate", "mid_range"),
        "assisted": ("ast_share", "passing"), "top3_usage": ("usage_rate", "shot_creation"),
        "orb": ("orb_share", "off_rebounding"), "drb": ("drb_share", "def_rebounding"),
        "ftr": ("trip_rate", "drawing_fouls"), "turnovers": ("usage_rate", "ball_security"),
        "opp_inside": ("rim_effect", "rim_protection"), "opp_three": ("three_att_effect", "perimeter_defense"),
        "opp_tov": ("stl_rate", "steals"), "opp_ftr": ("foul_rate", "discipline"),
    }
    pick = picks.get(metric)
    if pick is None:
        return []
    volume, rating = pick
    d = pm.merge(ratings[["player_id", "player", rating, f"{rating}_low_data", "mpg"]], on="player_id", suffixes=("", "_r"))
    d = d[(d.mpg_r >= 10) & ~d[f"{rating}_low_data"]]
    # how much he contributes matters more than how high he rates
    d = d.assign(weight=d[volume] * d.mpg_r).sort_values("weight", ascending=False).head(3)
    # shown as on the player card: tiers stay tiers
    return [{"name": short_name(r.player_r), "rating": int(getattr(r, rating)), "attribute": rating,
             "shown": display_value(rating, int(getattr(r, rating)), bool(getattr(r, "three_non_shooter", False)), None, bool(getattr(r, "mid_non_shooter", False)))}
            for r in d.itertuples()]


def assist_pairs(t: Tables, season: str, team: str, names: dict[str, str], count: int = 4) -> list[dict]:
    s = t.shots[(t.shots.season == season) & (t.shots.team == team) & t.shots.made & t.shots.assisted]
    s = s[s.assist_player_id != ""]
    if s.empty:
        return []
    pairs = s.groupby(["assist_player_id", "player_id"]).agg(n=("value", "size"), pts=("value", "sum")).sort_values("n", ascending=False).head(count)
    return [{"from": short_name(names.get(a, a)), "to": short_name(names.get(b, b)), "count": int(r.n), "points": int(r.pts)} for (a, b), r in pairs.iterrows()]


def describe(metrics: list[dict]) -> list[str]:
    """Sentences for what stands out, strongest first. Only stable tendencies get one."""
    candidates = []
    for x in metrics:
        if not x["stable"] or x["key"] in ("drb",):
            continue
        n = x["teams"]
        top = x["rank"] <= 3
        bottom = x["rank"] > n - 3
        if not top and not bottom:
            continue
        m = BY_KEY[x["key"]]
        phrase = m.high if top else m.low
        place = x["rank"] if top else n - x["rank"] + 1
        order = "en yüksek" if top else "en düşük"
        where = f"ligin {order} değeri" if place == 1 else f"ligin {place}. {order} değeri"
        value = f"{x['value']:.{m.digits}f}{m.unit}"
        league = f"{x['league']:.{m.digits}f}{m.unit}"
        candidates.append((abs(x["z"]), f"{m.label} {value}: {where} (lig {league}). Yani {phrase} bir takım."))
    candidates.sort(key=lambda c: -c[0])
    return [c[1] for c in candidates[:5]]


def similar_teams(table: pd.DataFrame, code: str, names: dict[str, str], stable: list[str], count: int = 2) -> list[dict]:
    z = table[stable]
    z = (z - z.mean()) / z.std().replace(0, 1)
    gaps = ((z - z.loc[code]) ** 2).sum(axis=1).drop(code).sort_values()
    return [{"code": c, "name": names.get(c, c)} for c in gaps.index[:count]]


def build(t: Tables | None = None) -> dict:
    t = t or load_tables()
    counts = team_game_counts(t)
    stable_table = load_stability()
    ratings_all = pd.read_parquet(TABLES_DIR / "ratings_season.parquet")
    metrics_all = pd.read_parquet(TABLES_DIR / "player_metrics.parquet")
    games = pd.read_parquet(TABLES_DIR / "games.parquet")
    out: dict = {"stability": stable_table, "groups": GROUPS, "seasons": {}}
    for season, part in counts.groupby("season"):
        names_players = dict(zip(t.player_games[t.player_games.season == season].player_id, t.player_games[t.player_games.season == season].player))
        g = games[games.season == season]
        team_names = dict(zip(g.home, g.home_name)) | dict(zip(g.away, g.away_name))
        needed = sorted({m.num for m in METRICS} | {m.den for m in METRICS} | {"points", "opp_points", "opp_poss"})
        totals = part.groupby("team")[needed].sum()
        table = pd.DataFrame({m.key: rate(totals, m) for m in METRICS})
        league = {m.key: float(m.scale * totals[m.num].sum() / totals[m.den].sum()) for m in METRICS}
        stable_keys = [m.key for m in METRICS if stable_table.get(m.key, {}).get("first_ten_vs_rest", 0) >= MIN_STABILITY]
        result = {}
        for code in table.index:
            r = ratings_all[(ratings_all.season == season) & (ratings_all.team == code)]
            pm = metrics_all[(metrics_all.season == season) & (metrics_all.team == code)]
            rows = []
            for m in METRICS:
                v = float(table.loc[code, m.key])
                sd = float(table[m.key].std()) or 1.0
                stab = stable_table.get(m.key, {})
                rows.append({"key": m.key, "label": m.label, "group": m.group, "value": round(v, 2), "unit": m.unit, "digits": m.digits,
                             "league": round(league[m.key], 2), "z": round((v - float(table[m.key].mean())) / sd, 2),
                             "rank": int(table[m.key].rank(ascending=False, method="min")[code]), "teams": int(len(table)),
                             "low": round(float(table[m.key].min()), 2), "high": round(float(table[m.key].max()), 2),
                             "stable": m.key in stable_keys, "stability": stab.get("first_ten_vs_rest"), "hint": m.hint,
                             "carriers": _carriers(r, pm, m.key)})
            games_played = int(totals.loc[code, "games"])
            off = 100 * totals.loc[code, "points"] / totals.loc[code, "poss"]
            dfn = 100 * totals.loc[code, "opp_points"] / totals.loc[code, "opp_poss"]
            net = (100 * totals.points / totals.poss) - (100 * totals.opp_points / totals.opp_poss)
            result[code] = {"code": code, "name": team_names.get(code, code), "games": games_played, "early": games_played < EARLY_SEASON_GAMES,
                            "summary": describe(rows), "metrics": rows,
                            "efficiency": {"off": round(float(off), 1), "def": round(float(dfn), 1), "net": round(float(off - dfn), 1),
                                           "net_rank": int(net.rank(ascending=False, method="min")[code]), "teams": int(len(net))},
                            "rotation": rotation_table(t, season, code, names_players), "assist_pairs": assist_pairs(t, season, code, names_players),
                            "similar": similar_teams(table, code, team_names, stable_keys) if stable_keys else []}
        out["seasons"][season] = result
    STYLE_FILE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    res = build()
    for season, teams in res["seasons"].items():
        print(season, len(teams), "teams")
