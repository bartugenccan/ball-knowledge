"""A commentator's account of a game, written by rules from what the engine produced.

Every sentence comes from a counted fact, so nothing can be made up. Several wordings per situation, picked
by the facts themselves, keep games from reading alike: the same game always reads the same.

Names and numbers take no Turkish case endings here. Those endings depend on sounds we cannot guess
reliably for foreign names, so "Fenerbahçe üçlükte 5/8 buldu", never "Fenerbahçe'nin".

Only what the data knows: no screens, no play calls, no one guarding anyone.
"""

from __future__ import annotations

import zlib

from bk.match.narrate import ATTRIBUTE_LABEL

CLUB = {"ASV": "ASVEL", "BAR": "Barcelona", "BAS": "Baskonia", "BER": "ALBA Berlin", "BES": "Beşiktaş", "DUB": "Dubai", "HTA": "Hapoel Tel Aviv", "IST": "Anadolu Efes",
        "MAD": "Real Madrid", "MCO": "Monaco", "MIL": "Milano", "MUN": "Bayern Münih", "OLY": "Olympiacos", "PAM": "Valencia", "PAN": "Panathinaikos", "PAR": "Partizan",
        "PRS": "Paris", "RED": "Kızılyıldız", "TEL": "Maccabi Tel Aviv", "ULK": "Fenerbahçe", "VIR": "Virtus", "ZAL": "Zalgiris"}
RUN_BIG = 10
HOT_THREES = (4, 0.5)       # at least this many attempts at this rate or better
COLD_THREES = (5, 0.2)
MANY_TURNOVERS = 5
SCORER_NIGHT = 8            # points in one quarter worth naming


def club(code: str) -> str:
    return CLUB.get(code, code)


def pick(key: str, options: list[str]) -> str:
    """The same facts always choose the same wording."""
    return options[zlib.crc32(key.encode("utf-8")) % len(options)]


def _threes(text: str) -> tuple[int, int]:
    made, tried = text.split("/")
    return int(made), int(tried)


def _margin_line(home: str, away: str, h: int, a: int) -> str:
    return f"{club(home)} {h}, {club(away)} {a}"


def _rating_of(events: list[dict], name: str) -> str | None:
    """A rating note the events carry for this player, when one stood out."""
    short = name
    for e in events:
        if e.get("note") and e["event"] == "make" and e["text"].split(":")[0].split(". ")[-1] == short:
            return e["note"]
    return None


def quarter_story(p: dict, before: tuple[int, int], events: list[dict], home: str, away: str) -> str:
    """One period as a few sentences."""
    key = f"{p['period']}|{p['home']}|{p['away']}"
    h_points, a_points = p["home_points"], p["away_points"]
    label = p["label"]
    leader_before = (before[0] > before[1]) - (before[0] < before[1])
    leader_after = (p["home"] > p["away"]) - (p["home"] < p["away"])
    won, lost = (home, away) if h_points > a_points else (away, home)
    gap = abs(h_points - a_points)
    parts: list[str] = []
    if gap == 0:
        parts.append(pick(key, [f"{label} {h_points}-{a_points} eşit geçti.", f"{label} iki takım da {h_points} sayı buldu, fark değişmedi."]))
    elif gap >= 8:
        parts.append(pick(key, [f"{label} {club(won)} damgasını vurdu: {max(h_points, a_points)}-{min(h_points, a_points)}.", f"{club(won)} {label.lower()} tek taraflı oynadı, {max(h_points, a_points)}-{min(h_points, a_points)} aldı.",
                                f"{label} {club(lost)} için zor geçti: {min(h_points, a_points)} sayıya karşılık {max(h_points, a_points)} yedi."]))
    else:
        parts.append(pick(key, [f"{label} {club(won)} {max(h_points, a_points)}-{min(h_points, a_points)} önde kapattı.", f"{club(won)} {label.lower()} {max(h_points, a_points)}-{min(h_points, a_points)} kazandı."]))

    for run in p.get("runs", []):
        if run["points"] >= RUN_BIG:
            parts.append(pick(key + "run", [f"Çeyreğin kırılma anı {club(run['team'])} serisiydi: {run['points']}-0.", f"{club(run['team'])} {run['points']}-0 seriyle maçın dengesini oynattı."]))
        else:
            parts.append(f"{club(run['team'])} {run['points']}-0 seri yakaladı.")

    top = [t for t in p.get("top", []) if t["points"] >= SCORER_NIGHT][:1]
    for t in top:
        note = _rating_of(events, t["name"])
        who = f"{t['name']} ({note})" if note else t["name"]
        parts.append(pick(key + "top", [f"{who} {t['points']} sayıyla öne çıktı.", f"{who} çeyreğin en üretken ismiydi: {t['points']} sayı.", f"Hücumu taşıyan isim {who} oldu, {t['points']} sayı."]))

    for code in (home, away):
        made, tried = _threes(p["threes"][code])
        if tried >= HOT_THREES[0] and made / tried >= HOT_THREES[1]:
            parts.append(pick(key + code + "hot", [f"{club(code)} üçlükte {made}/{tried} ile sıcaktı.", f"{club(code)} dış şutta iyi gitti: {made}/{tried} üçlük."]))
        elif tried >= COLD_THREES[0] and made / tried <= COLD_THREES[1]:
            parts.append(pick(key + code + "cold", [f"{club(code)} üçlükte {made}/{tried} ile soğuk kaldı.", f"{club(code)} dış şutu bulamadı: {made}/{tried} üçlük."]))
        if p["turnovers"][code] >= MANY_TURNOVERS:
            parts.append(pick(key + code + "to", [f"{club(code)} {p['turnovers'][code]} top kaybıyla işini zorlaştırdı.", f"{p['turnovers'][code]} top kaybı {club(code)} ritmini bozdu."]))

    trouble = [e for e in events if e["event"] == "sub" and ("faul sıkıntısı" in e["text"] or "oyun dışı" in e["text"])]
    if trouble:
        team = trouble[0].get("team")
        name = trouble[0]["text"].split(", ")[-1].split(" çıktı")[0].split("Değişiklik: ")[-1]
        parts.append(f"{club(team)} faul sıkıntısı yüzünden rotasyonunu değiştirmek zorunda kaldı ({name}).")

    if leader_before != leader_after and leader_after != 0 and p["period"] > 1:
        parts.append(f"Üstünlük el değiştirdi: {_margin_line(home, away, p['home'], p['away'])}.")
    else:
        parts.append(f"Skor: {_margin_line(home, away, p['home'], p['away'])}.")
    return " ".join(parts)


def game_story(events: list[dict], periods: list[dict], moments: list[dict], home: str, away: str) -> list[dict]:
    """The whole game, one paragraph per period and a closing one."""
    out = []
    before = (0, 0)
    for p in periods:
        part = [e for e in events if e["period"] == p["period"]]
        out.append({"title": p["label"], "text": quarter_story(p, before, part, home, away)})
        before = (p["home"], p["away"])
    if periods:
        last = periods[-1]
        winner, loser = (home, away) if last["home"] > last["away"] else (away, home)
        gap = abs(last["home"] - last["away"])
        high, low = max(last["home"], last["away"]), min(last["home"], last["away"])
        key = f"end|{high}|{low}"
        if gap <= 5:
            end = pick(key, [f"Maç son saniyelere kadar açık kaldı, {club(winner)} {high}-{low} kazandı.", f"{club(winner)} sıkı maçı {high}-{low} aldı."])
        elif gap >= 15:
            end = pick(key, [f"{club(winner)} {high}-{low} rahat kazandı.", f"Fark büyüdü, {club(loser)} geri dönemedi: {high}-{low}."])
        else:
            end = pick(key, [f"{club(winner)} farkı korudu ve {high}-{low} kazandı.", f"Sonuç {club(winner)} lehine: {high}-{low}."])
        decisive = next((m["text"] for m in moments if m["kind"] == "winner"), None)
        if decisive:
            end += " " + decisive + "."
        out.append({"title": "Son düdük", "text": end})
    return out


def _leaders_text(rows: list[dict]) -> str:
    return ", ".join(f"{x['name']} ({ATTRIBUTE_LABEL.get(x['attribute'], x['attribute'])} {x.get('label') or x['rating']})" for x in rows)


# Thresholds and tone come from how often each kind of claim came true, measured with the squad we would really
# have before a game (data/audit/match_claim_card_likely.md, 472 games). Below the first level a claim is left out;
# "firm" ones are stated plainly and the rest with care. Shot making came true only 58-61% of the time but decides
# most games, so it is always hedged. Offensive rebounds came true 57-63%, so they are hedged too. A gap in paint
# attempts came true 55%, below the bar, so only the three-point gap is told as a difference in style.
MIN_POINTS = {"shooting": 1.3, "turnovers": 1.2, "rebounds": 1.2, "free_throws": 1.0}
SHOT_STYLE_GAP = 4.0        # attempts. Who shoots more threes says what kind of game it is, not who wins it


def preview(report: dict) -> list[dict]:
    """Where each side should have the edge before tip-off, largest first. No edge, no sentence."""
    home, away = report["home"]["code"], report["away"]["code"]
    rows = []
    for e in sorted(report["edges"], key=lambda x: -abs(x["points"])):
        floor = MIN_POINTS.get(e["key"])
        if floor is None or abs(e["points"]) < floor:
            continue
        side, other = (home, away) if e["points"] > 0 else (away, home)
        unit = e["unit"]
        own, opp = (e["home"], e["away"]) if side == home else (e["away"], e["home"])
        numbers = f"{own}{unit} ve {opp}{unit}"
        who = _leaders_text(e["leaders"].get(side, [])[:2])
        key = f"{e['key']}|{side}|{own}"
        if e["key"] == "turnovers":
            text = pick(key, [f"{club(side)} topu biraz daha iyi koruyacak gibi: beklenen top kaybı {numbers}.", f"Top kaybında {club(side)} hafif önde görünüyor: {numbers}."])
            rival = _leaders_text(e["leaders"].get(other, [])[:1])
            if rival:
                text += f" {club(other)} tarafında baskıyı kuracak isim {rival}."
        elif e["key"] == "rebounds":
            text = pick(key, [f"Hücum ribaundunda {club(side)} biraz önde görünüyor: beklenen pay {numbers}.", f"{club(side)} ikinci şansları biraz daha çok üretecek gibi: hücum ribaundu payı {numbers}."])
            text += " Bu tek başına maç kazandırmaz, ama fazladan hücum demek."
        elif e["key"] == "free_throws":
            text = pick(key, [f"{club(side)} çizgiden daha çok sayı bulacak: {numbers}.", f"Serbest atışta {club(side)} önde: {numbers}."])
        else:
            text = pick(key, [f"Şut veriminde {club(side)} biraz önde görünüyor: {numbers}.", f"{club(side)} şutunu biraz daha verimli kullanacak gibi: {numbers}."])
        if who and e["key"] != "turnovers":
            text += f" Bunun arkasındaki isimler: {who}."
        text += f" Karşılığı yaklaşık {abs(e['points']):.1f} sayı."
        rows.append({"key": e["key"], "team": side, "points": round(abs(e["points"]), 1), "text": text})
    teams = report["teams"]
    gap = teams[home]["f3a"]["mean"] - teams[away]["f3a"]["mean"]
    if abs(gap) >= SHOT_STYLE_GAP:
        side, other = (home, away) if gap > 0 else (away, home)
        rows.append({"key": "style", "team": side, "points": 0.0,
                     "text": f"Oyun tarzı farklı: {club(side)} üçlüğe daha çok yaslanacak ({teams[side]['f3a']['mean']:.0f} ve {teams[other]['f3a']['mean']:.0f} şut)."})
    if not any(r["key"] != "style" for r in rows):
        rows.insert(0, {"key": "even", "team": None, "points": 0.0, "text": "Rakamlarda belirgin bir üstünlük yok: bu maç o geceki şuta kalacak gibi."})
    return rows


def coach_notes(report: dict, what_if: list[dict]) -> list[dict]:
    """What each side's game depends on most, largest first. Sizes come from replaying the game with one thing changed."""
    out = []
    for code in (report["home"]["code"], report["away"]["code"]):
        rows = sorted((w for w in what_if if w["team"] == code and w["significant"]), key=lambda w: -w["margin"])[:3]
        if not rows:
            out.append({"team": code, "items": [f"{club(code)} için tek bir konu öne çıkmıyor."]})
            continue
        items = [f"{w['label']}: beklenen fark {w['margin']:+.1f} sayı değişir." for w in rows]
        out.append({"team": code, "items": items})
    return out


def tempo_line(report: dict) -> str:
    """The pace to expect, against the league's usual."""
    home, away = report["home"]["code"], report["away"]["code"]
    poss = (report["teams"][home]["poss"]["mean"] + report["teams"][away]["poss"]["mean"]) / 2
    total = report["score"]["total"]["mean"]
    if poss >= 75:
        return f"Tempo yüksek bekleniyor: takım başına yaklaşık {poss:.0f} hücum, toplam {total:.0f} sayı civarı."
    if poss <= 72:
        return f"Yavaş bir maç bekleniyor: takım başına yaklaşık {poss:.0f} hücum, toplam {total:.0f} sayı civarı."
    return f"Tempo lig ortalamasına yakın: takım başına yaklaşık {poss:.0f} hücum, toplam {total:.0f} sayı civarı."
