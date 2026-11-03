"""Example sets shipped with the app. Coaches start from these and edit.

Slots: 1 PG, 2 SG, 3 SF, 4 PF, 5 C. Defenders are keyed by the slot they guard.

Every set includes a "defense blows it up" branch ending in a late-clock,
self-created shot. Without it, a set that always reaches a clean look would
overstate real half-court efficiency. Its weight grows with the defender's
rating (favors: "def").
"""


def breakdown(ball: str, shooter: str | None = None, weight: float = 0.18) -> tuple[dict, dict]:
    shooter = shooter or ball
    option = {"to": "late_clock", "weight": weight, "label": "Savunma okudu, set bozuldu", "favors": "def",
              "edge": {"off": [ball, "passing"], "def": [ball, "perimeter_defense"]}}
    node = {"type": "shot", "shooter": shooter, "zone": "above_break3", "creation": "dribble", "openness": 0.15,
            "defender": shooter, "label": f"{shooter} şut saati sonu zor şut"}
    return option, node

HORNS_FLARE = {
    "id": "horns-flare", "name": "Horns Flare",
    "description": "Horns girişi: 5 top sürene perde, 4 kenarda 2'ye flare perdesi.",
    "start": "entry",
    "nodes": {
        "entry": {"type": "action", "kind": "screen", "ball": "1", "label": "5, 1'e top perdesi",
                  "pos": {"1": [0, 8], "2": [-6.6, 0.5], "3": [6.6, 0.5], "4": [-2.5, 6], "5": [2.5, 6]},
                  "options": [
                      {"to": "pnr_drive", "weight": 0.45, "label": "1 perdeden sürüyor",
                       "edge": {"off": ["1", "shot_creation"], "def": ["1", "perimeter_defense"]}},
                      {"to": "roll", "weight": 0.25, "label": "5 rim'e dönüyor (roll)",
                       "edge": {"off": ["5", "finishing"], "def": ["5", "rim_protection"]}},
                      {"to": "flare_pass", "weight": 0.30, "label": "Ters taraf: 4 flare perdesi 2'ye"}]},
        "pnr_drive": {"type": "action", "kind": "drive", "ball": "1", "label": "1 boyalı alana giriyor",
                      "options": [
                          {"to": "pullup", "weight": 0.40, "label": "Pull-up orta mesafe"},
                          {"to": "layup", "weight": 0.35, "label": "Turu tamamlıyor",
                           "edge": {"off": ["1", "finishing"], "def": ["5", "rim_protection"]}},
                          {"to": "kick_corner", "weight": 0.25, "label": "Köşeye çıkarıyor (3)",
                           "edge": {"off": ["1", "passing"], "def": ["3", "perimeter_defense"]}}]},
        "pullup": {"type": "shot", "shooter": "1", "zone": "mid", "creation": "dribble", "openness": 0.35,
                   "defender": "1", "label": "1 pull-up"},
        "layup": {"type": "shot", "shooter": "1", "zone": "rim", "creation": "dribble", "openness": 0.40,
                  "defender": "1", "help": "5", "label": "1 turnike"},
        "kick_corner": {"type": "shot", "shooter": "3", "zone": "corner3", "creation": "catch", "openness": 0.70,
                        "defender": "3", "label": "3 köşe üçlük"},
        "roll": {"type": "shot", "shooter": "5", "zone": "rim", "creation": "catch", "openness": 0.55,
                 "defender": "5", "help": "4", "label": "5 roll bitiriş"},
        "flare_pass": {"type": "action", "kind": "pass", "ball": "1", "label": "1, flare'den çıkan 2'ye pas",
                       "options": [
                           {"to": "flare_three", "weight": 0.75, "label": "2 catch & shoot",
                            "edge": {"off": ["2", "three_point"], "def": ["2", "perimeter_defense"]}},
                           {"to": "flare_attack", "weight": 0.25, "label": "Close-out'a karşı sürüş"}]},
        "flare_three": {"type": "shot", "shooter": "2", "zone": "above_break3", "creation": "catch",
                        "openness": 0.60, "defender": "2", "label": "2 flare üçlük"},
        "flare_attack": {"type": "shot", "shooter": "2", "zone": "paint", "creation": "dribble",
                         "openness": 0.45, "defender": "2", "help": "4", "label": "2 close-out sürüşü"},
    },
}

SPAIN_PNR = {
    "id": "spain-pnr", "name": "Spain Pick & Roll",
    "description": "5 top perdesi, 2 roll eden 5'in savunmacısına arka perde koyup üçlüğe açılıyor.",
    "start": "entry",
    "nodes": {
        "entry": {"type": "action", "kind": "screen", "ball": "1", "label": "5 top perdesi + 2 arka perde",
                  "options": [
                      {"to": "roll_lob", "weight": 0.35, "label": "5 rim'e",
                       "edge": {"off": ["5", "finishing"], "def": ["5", "rim_protection"]}},
                      {"to": "pop_two", "weight": 0.35, "label": "2 perdeden sonra üçlüğe açılıyor",
                       "edge": {"off": ["2", "three_point"], "def": ["2", "perimeter_defense"]}},
                      {"to": "pg_shot", "weight": 0.30, "label": "1 kendi bitiriyor",
                       "edge": {"off": ["1", "shot_creation"], "def": ["1", "perimeter_defense"]}}]},
        "roll_lob": {"type": "shot", "shooter": "5", "zone": "rim", "creation": "catch", "openness": 0.60,
                     "defender": "5", "help": "4", "label": "5 lob / roll"},
        "pop_two": {"type": "shot", "shooter": "2", "zone": "above_break3", "creation": "catch", "openness": 0.65,
                    "defender": "2", "label": "2 pop üçlük"},
        "pg_shot": {"type": "action", "kind": "drive", "ball": "1", "label": "1 okuma",
                    "options": [
                        {"to": "pg_three", "weight": 0.5, "label": "Perde arkası üçlük"},
                        {"to": "pg_float", "weight": 0.5, "label": "Floater"}]},
        "pg_three": {"type": "shot", "shooter": "1", "zone": "above_break3", "creation": "dribble",
                     "openness": 0.45, "defender": "1", "label": "1 pull-up üçlük"},
        "pg_float": {"type": "shot", "shooter": "1", "zone": "paint", "creation": "dribble", "openness": 0.40,
                     "defender": "1", "help": "5", "label": "1 floater"},
    },
}

POST_UP = {
    "id": "post-up", "name": "Low Post Isolation",
    "description": "5 sol blokta top alıyor; şut, faul ya da dışarı pas.",
    "start": "entry_pass",
    "nodes": {
        "entry_pass": {"type": "action", "kind": "pass", "ball": "1", "label": "Posta giriş pası",
                       "options": [{"to": "post", "weight": 1.0, "label": "5 topu alıyor"}]},
        "post": {"type": "action", "kind": "post", "ball": "5", "label": "5 post hamlesi",
                 "options": [
                     {"to": "post_finish", "weight": 0.6, "label": "Hook / up-and-under",
                      "edge": {"off": ["5", "finishing"], "def": ["5", "rim_protection"]}},
                     {"to": "kick_out", "weight": 0.4, "label": "Çift sıkıştırma → dışarı pas",
                      "edge": {"off": ["5", "passing"], "def": ["5", "steals"]}}]},
        "post_finish": {"type": "shot", "shooter": "5", "zone": "paint", "creation": "dribble", "openness": 0.30,
                        "defender": "5", "label": "5 post bitiriş"},
        "kick_out": {"type": "shot", "shooter": "3", "zone": "above_break3", "creation": "catch", "openness": 0.70,
                     "defender": "3", "label": "3 dışarıdan üçlük"},
    },
}

LIBRARY = {s["id"]: s for s in (HORNS_FLARE, SPAIN_PNR, POST_UP)}


def _with_breakdown(s: dict, action: str, ball: str, shooter: str | None = None) -> dict:
    option, node = breakdown(ball, shooter)
    s["nodes"][action]["options"].append(option)
    s["nodes"]["late_clock"] = node
    return s


_with_breakdown(HORNS_FLARE, "entry", "1")
_with_breakdown(SPAIN_PNR, "entry", "1")
_with_breakdown(POST_UP, "post", "5", shooter="1")
