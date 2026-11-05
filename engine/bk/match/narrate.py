"""Turn events into plain Turkish play-by-play, for simulated and real games alike.

Sentences avoid suffixes on player names: foreign names take Turkish case endings by rules we cannot
guess reliably, so a line reads "Hezonja: köşeden üçlük, isabet" rather than "Hezonja'dan".

A line says only what the data knows. There is no play type or defender in the feed, so nothing here
speaks of screens, drives or who guarded whom.
"""

from __future__ import annotations

from collections import defaultdict

ZONE_TEXT = {"inside": "boyalı alan", "mid": "orta mesafe", "corner3": "köşeden üçlük", "above_break3": "üçlük"}
ATTRIBUTE_LABEL = {"finishing": "Bitiricilik", "mid_range": "Orta Mesafe", "three_point": "Üçlük", "shot_blocking": "Blok", "steals": "Top Çalma",
                   "off_rebounding": "Hücum Ribaundu", "def_rebounding": "Savunma Ribaundu", "passing": "Pas", "drawing_fouls": "Faul Alma",
                   "free_throw": "Serbest Atış", "discipline": "Faul Disiplini", "shot_creation": "Şut Yaratma", "ball_security": "Top Güvenliği"}
ZONE_ATTRIBUTE = {"inside": "finishing", "mid": "mid_range", "corner3": "three_point", "above_break3": "three_point"}
ROMAN = {"II", "III", "IV"}
NOTE_HIGH = 16
NOTE_LOW = 6


def full_name(raw: str) -> str:
    """'HEZONJA, MARIO' -> 'Mario Hezonja'."""
    if "," not in raw:
        return _title(raw)
    last, first = raw.split(",", 1)
    return f"{_title(first.strip())} {_title(last.strip())}".strip()


def short_name(raw: str) -> str:
    """Only the family name: a play-by-play line has little room."""
    return _title(raw.split(",", 1)[0].strip()) if "," in raw else _title(raw)


def _title(s: str) -> str:
    def word(w: str) -> str:
        if w.upper() in ROMAN:
            return w.upper()
        for sep in ("-", "'"):
            if sep in w:
                return sep.join(word(p) for p in w.split(sep))
        lower = w.lower()
        if lower.startswith("mc") and len(w) > 2:
            return "Mc" + lower[2:].capitalize()
        return w[:1].upper() + lower[1:]

    return " ".join(word(w) for w in s.split())


def rating_note(ratings: dict[str, dict], player_id: str | None, attribute: str) -> str | None:
    """A rating worth quoting next to an event: only clear strengths and weaknesses, and only with enough data."""
    if player_id is None:
        return None
    info = ratings.get(player_id)
    if not info or attribute in info.get("low_data", ()):
        return None
    value = info["values"].get(attribute)
    if value is None or NOTE_LOW < value < NOTE_HIGH:
        return None
    shown = info.get("labels", {}).get(attribute, value)
    return f"{ATTRIBUTE_LABEL[attribute]} {shown}"


def line(e: dict, ratings: dict[str, dict]) -> tuple[str, str | None]:
    """The text of one event, plus an optional rating note."""
    kind = e["event"]
    name = short_name(e["player"]) if e.get("player") else ""
    pid = e.get("player_id")
    if kind == "make":
        zone = ZONE_TEXT[e["zone"]]
        prefix = {"transition": "Hızlı hücum. ", "putback": "Hücum ribaundu sonrası. "}.get(e.get("context"), "")
        tail = f", asist {short_name(e['assist'])}" if e.get("assist") else ""
        return f"{prefix}{name}: {zone}, isabet{tail}", rating_note(ratings, pid, ZONE_ATTRIBUTE[e["zone"]])
    if kind == "miss":
        zone = ZONE_TEXT[e["zone"]]
        if e.get("blocked_by"):
            return f"{name}: {zone}, blok {short_name(e['blocked_by'])}", rating_note(ratings, e.get("blocked_by_id"), "shot_blocking")
        return f"{name}: {zone}, kaçtı", None
    if kind == "orb":
        return f"{name}: hücum ribaundu", rating_note(ratings, pid, "off_rebounding")
    if kind == "drb":
        return f"{name}: savunma ribaundu", rating_note(ratings, pid, "def_rebounding")
    if kind == "steal":
        lost = f" ({short_name(e['lost_by'])} kaybetti)" if e.get("lost_by") else ""
        return f"{name}: top çaldı{lost}", rating_note(ratings, pid, "steals")
    if kind == "turnover":
        if e.get("kind") == "offensive_foul":
            return f"{name}: hücum faulü ({e.get('fouls', '')}. faul), top kaybı", None
        return f"{name}: top kaybı", None
    if kind == "foul":
        n = e.get("fouls")
        count = f" ({n}. faul)" if n else ""
        drawn = short_name(e["drawn"]) if e.get("drawn") else ""
        note = rating_note(ratings, pid, "discipline") if (n or 0) >= 3 else None
        foul_kind = e.get("kind")
        if foul_kind == "shooting":
            return f"{name}: şut faulü{count}, {drawn} çizgide", note
        if foul_kind == "and_one":
            return f"{name}: faul{count}, {drawn} için ek atış", note
        if foul_kind == "intentional":
            return f"{name}: saati durdurmak için faul{count}", note
        if foul_kind == "penalty":
            return f"{name}: faul{count}, takım faulü sınırı aşıldı", note
        return f"{name}: faul{count}", note
    if kind == "ft":
        return f"{name}: serbest atış {e['made']}/{e['shots']}", rating_note(ratings, pid, "free_throw") if e["shots"] >= 2 else None
    if kind == "sub":
        into = ", ".join(short_name(x) for x in e["into"])
        out = ", ".join(short_name(x) for x in e["out"])
        reason = {"foul_trouble": " (faul sıkıntısı)", "foul_out": " (5 faul, oyun dışı)"}.get(e.get("reason", ""), "")
        return f"Değişiklik: {into} girdi, {out} çıktı{reason}", None
    if kind == "timeout":
        run = e.get("run") or 0
        return (f"Mola: rakibin {run}-0 serisini kesmek için" if run >= 6 else "Mola"), None
    if kind == "tv_timeout":
        return "TV molası", None
    if kind == "period_start":
        p = e["period"]
        return (f"{p}. çeyrek başladı" if p <= 4 else f"{p - 4}. uzatma başladı"), None
    if kind == "period_end":
        p = e["period"]
        return (f"{p}. çeyrek bitti" if p <= 4 else f"{p - 4}. uzatma bitti"), None
    return kind, None


def narrate(events: list[dict], ratings: dict[str, dict]) -> list[dict]:
    """Keep what the page needs from each event: its text, the score, who and where."""
    out = []
    for e in events:
        text, note = line(e, ratings)
        row = {"event": e["event"], "period": e["period"], "clock": e["clock"], "elapsed": e["elapsed"], "team": e.get("team"),
               "home": e["home"], "away": e["away"], "text": text}
        if note:
            row["note"] = note
        if e["event"] in ("make", "miss"):
            row["value"] = e.get("value")
            row["zone"] = e.get("zone")
            row["player_id"] = e.get("player_id")
            if e.get("coord"):
                row["coord"] = e["coord"]
        if e["event"] == "period_start" and e.get("starters"):
            row["starters"] = {k: [short_name(x) for x in v] for k, v in e["starters"].items()}
        if e["event"] == "make" and e.get("p_make"):
            row["p_make"] = e["p_make"]
        out.append(row)
    return out


def scoring_runs(events: list[dict], min_points: int = 8, start: tuple[int, int] = (0, 0)) -> list[dict]:
    """Stretches of unanswered points, from the event list. start is the score before the first event."""
    runs, current = [], None
    last = start
    for e in events:
        now = (e["home"], e["away"])
        if now == last:
            continue
        scorer = 0 if now[0] > last[0] else 1
        pts = (now[0] - last[0]) + (now[1] - last[1])
        if current and current["side"] == scorer:
            current["points"] += pts
            current["end_period"], current["end_clock"], current["end_home"], current["end_away"] = e["period"], e["clock"], now[0], now[1]
        else:
            if current and current["points"] >= min_points:
                runs.append(current)
            current = {"side": scorer, "team": e.get("team"), "points": pts, "period": e["period"], "clock": e["clock"],
                       "end_period": e["period"], "end_clock": e["clock"], "end_home": now[0], "end_away": now[1]}
        last = now
    if current and current["points"] >= min_points:
        runs.append(current)
    return runs


def key_moments(events: list[dict], home: str, away: str) -> list[dict]:
    """What a fan would retell after the game, in order. Everything comes from the events themselves."""
    moments: list[dict] = []

    def add(e_period: int, clock: str, elapsed: float, kind: str, text: str) -> None:
        moments.append({"period": e_period, "clock": clock, "elapsed": elapsed, "kind": kind, "text": text})

    def label(period: int) -> str:
        return f"{period}. çeyrek" if period <= 4 else f"{period - 4}. uzatma"

    elapsed_at: dict[tuple[int, str], float] = {(e["period"], e["clock"]): e["elapsed"] for e in events}
    for r in scoring_runs(events):
        team = home if r["side"] == 0 else away
        add(r["period"], r["clock"], elapsed_at.get((r["period"], r["clock"]), 0.0), "run",
            f"{team} {r['points']}-0'lık seri ({label(r['period'])}, {r['clock']}): skor {r['end_home']}-{r['end_away']}")

    last_leader = None
    max_lead = (0, -1)
    late_changes = 0
    last_score = None
    for e in events:
        if e["event"] == "sub" and e.get("reason") == "foul_out":
            add(e["period"], e["clock"], e["elapsed"], "foul_out", f"{e.get('team')}: {short_name(e['out'][0])} 5 faulle oyun dışı")
        score = (e["home"], e["away"])
        if score == last_score:
            continue
        last_score = score
        margin = e["home"] - e["away"]
        if abs(margin) > max_lead[0]:
            max_lead = (abs(margin), e["elapsed"])
        leader = 0 if margin > 0 else 1 if margin < 0 else None
        if leader is not None:
            if last_leader is not None and leader != last_leader and e["period"] >= 4 and e["elapsed"] >= 2100:
                late_changes += 1
                add(e["period"], e["clock"], e["elapsed"], "lead", f"Son bölümde üstünlük değişti: {home if leader == 0 else away} öne geçti, {e['home']}-{e['away']}")
            last_leader = leader

    # the basket that took the lead for good
    final_home, final_away = events[-1]["home"], events[-1]["away"]
    if final_home != final_away:
        winner = 0 if final_home > final_away else 1
        decisive = None
        for e in events:
            if e["event"] not in ("make", "ft"):
                continue
            ahead = e["home"] > e["away"] if winner == 0 else e["away"] > e["home"]
            if not ahead:
                decisive = None
            elif decisive is None:
                decisive = e
        if decisive and decisive["period"] >= 4 and decisive["elapsed"] >= 2280:
            add(decisive["period"], decisive["clock"], decisive["elapsed"], "winner",
                f"Maçı koparan sayı: {short_name(decisive['player'])}, {decisive['home']}-{decisive['away']}")
    if any(e["period"] > 4 for e in events):
        tied = next(e for e in events if e["period"] > 4)
        add(tied["period"], tied["clock"], tied["elapsed"], "overtime", f"Maç uzatmaya gitti: {tied['home']}-{tied['away']}")
    moments.sort(key=lambda m: m["elapsed"])
    return moments


def quarter_summaries(events: list[dict], home: str, away: str) -> list[dict]:
    """A short account of each period, built from counted facts."""
    out = []
    start = (0, 0)
    for period in sorted({e["period"] for e in events}):
        part = [e for e in events if e["period"] == period]
        end = (part[-1]["home"], part[-1]["away"])
        scored = defaultdict(int)
        threes = {home: [0, 0], away: [0, 0]}
        turnovers = {home: 0, away: 0}
        for e in part:
            if e["event"] == "make":
                scored[(e["team"], e["player"])] += e["value"]
            if e["event"] == "ft":
                scored[(e["team"], e["player"])] += e["made"]
            if e["event"] in ("make", "miss") and e.get("value") == 3:
                threes[e["team"]][1] += 1
                threes[e["team"]][0] += e["event"] == "make"
            if e["event"] == "turnover":
                turnovers[e["team"]] += 1
            if e["event"] == "steal":
                other = home if e["team"] == away else away
                turnovers[other] += 1
        top = sorted(scored.items(), key=lambda kv: -kv[1])[:2]
        runs = scoring_runs(part, 8, start)
        out.append({"period": period, "label": f"{period}. çeyrek" if period <= 4 else f"{period - 4}. uzatma",
                    "home_points": end[0] - start[0], "away_points": end[1] - start[1], "home": end[0], "away": end[1],
                    "top": [{"team": k[0], "name": short_name(k[1]), "points": v} for k, v in top],
                    "threes": {k: f"{v[0]}/{v[1]}" for k, v in threes.items()}, "turnovers": turnovers,
                    "runs": [{"team": home if r["side"] == 0 else away, "points": r["points"]} for r in runs]})
        start = end
    return out
