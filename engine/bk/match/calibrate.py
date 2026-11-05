"""League-wide simulator constants, fitted on the reference seasons only.

    uv run python -m bk.match.calibrate

E2026 is the final-check season and never takes part. Anything that depends on a team or a player
is estimated later, from the games before the simulated one (bk.match.model).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from bk.config import TABLES_DIR
from bk.ratings.method import REFERENCE_SEASONS
from bk.ratings.metrics_v2 import load_tables

CALIBRATION_FILE = TABLES_DIR / "match_calibration.json"
ZONES = ("inside", "mid", "corner3", "above_break3")
MINUTES = 40
GOOD_SHOT = ["season", "gamecode", "seq"]


def seconds_sample(values: pd.Series, low: float, high: float, size: int = 400) -> list[float]:
    """Evenly spaced quantiles, so a draw is one list lookup during the game."""
    v = values.dropna()
    v = v[(v >= low) & (v <= high)]
    return [round(float(x), 1) for x in np.quantile(v, (np.arange(size) + 0.5) / size)]


def start_types(events: pd.DataFrame) -> pd.Series:
    """How the ball changed hands before each event: make, drb, steal, dead or period."""
    e = events.sort_values(["season", "gamecode", "seq"])
    labels, state, game = [], "period", None
    for key, kind in zip(zip(e.season, e.gamecode), e.type):
        if key != game:
            game, state = key, "period"
        labels.append(state)
        if kind in ("2FGM", "3FGM", "FTM"):
            state = "make"
        elif kind == "D":
            state = "drb"
        elif kind == "ST":
            state = "steal"
        elif kind == "TO" and state != "steal":
            state = "dead"
        elif kind in ("BP", "EP"):
            state = "period"
    return pd.Series(labels, index=e.index)


def rotation_templates(stints: pd.DataFrame, pg: pd.DataFrame) -> dict[str, list[float]]:
    """Average chance of being on court in each game minute, for starters and for bench players."""
    role = pg.set_index(["season", "gamecode", "player_id"]).starter
    s = stints[stints.start < MINUTES * 60].join(role, on=["season", "gamecode", "player_id"])
    games = pg[pg.minutes > 0].groupby("starter").size().astype(float)
    out = {}
    for starter, label in ((True, "starter"), (False, "bench")):
        seconds = np.zeros(MINUTES)
        part = s[s.starter == starter]
        for a, b in zip(part.start.to_numpy(), part.end.to_numpy()):
            first, last = int(a // 60), int(min(b, MINUTES * 60 - 1) // 60)
            for m in range(first, last + 1):
                seconds[m] += max(0.0, min(b, (m + 1) * 60) - max(a, m * 60))
        out[label] = [round(float(x), 4) for x in seconds / (60 * games[starter])]
    return out


def logit(p: float) -> float:
    return float(np.log(p / (1 - p)))


def calibrate() -> dict:
    t = load_tables()
    keep = lambda df: df[df.season.isin(REFERENCE_SEASONS)]  # noqa: E731
    shots, po, pg, ev = keep(t.shots), keep(t.possessions), keep(t.player_games), keep(t.events)
    trips, fouls, rb, stints = keep(t.trips), keep(t.fouls), keep(t.rebounds), keep(t.stints)
    n_poss = len(po)
    n_games = po.groupby(["season", "gamecode"]).ngroups

    s = shots[shots.zone_group.isin(ZONES)]
    first = s[s.since_orb.isna()]

    # how the ball changed hands, for first-chance shots only
    types = start_types(ev)
    ev_start = ev.loc[types.index, GOOD_SHOT].assign(start=types.to_numpy())
    joined = first.merge(ev_start, on=GOOD_SHOT, how="left")
    joined["trans"] = joined.context == "transition"
    p_trans = joined.groupby("start").trans.mean().round(4).to_dict()

    hc = s[s.context == "halfcourt"]
    level = {z: float(hc[hc.zone_group == z].made.mean()) for z in ZONES}

    make_delta: dict[str, dict[str, float]] = {}
    zone_mult: dict[str, dict[str, float]] = {}
    base_share = hc.zone_group.value_counts(normalize=True)
    three_base = float(base_share["corner3"] + base_share["above_break3"])
    for ctx in ("transition", "putback"):
        part = s[s.context == ctx]
        rates = part.groupby("zone_group").made.mean()
        share = part.zone_group.value_counts(normalize=True)
        make_delta[ctx] = {z: round(logit(float(rates[z])) - logit(level[z]), 4) for z in ZONES}
        three_share = float(share["corner3"] + share["above_break3"])
        zone_mult[ctx] = {"inside": round(float(share["inside"] / base_share["inside"]), 3),
                          "mid": round(float(share["mid"] / base_share["mid"]), 3),
                          "three": round(three_share / three_base, 3)}

    made = s[s.made]
    assisted = made.groupby(["context", "zone_group"]).assisted.mean().round(4)
    blocked = s.groupby("zone_group").blocked.mean().round(4).to_dict()

    # free-throw trips and fouls -----------------------------------------------------------
    kinds = trips.kind.value_counts()
    personal = fouls[fouls.foul_kind == "personal"]
    under_bonus = float((personal.team_fouls <= 4).mean())
    plain_shooting = float(kinds.get("shooting_2", 0) + kinds.get("shooting_3", 0))
    p_shooting_foul = plain_shooting / (n_poss * under_bonus)
    in_bonus_shooting = p_shooting_foul * n_poss * (1 - under_bonus)
    non_shooting = max(0.0, len(personal) - plain_shooting - kinds.get("and_one", 0) - in_bonus_shooting)
    three_share_of_trips = float(kinds.get("shooting_3", 0) / max(plain_shooting, 1))
    and_one = float(kinds.get("and_one", 0) / max(len(made), 1))

    # turnovers ---------------------------------------------------------------------------------
    n_to = float((ev.type == "TO").sum())
    steal_share = float((ev.type == "ST").sum() / n_to)
    off_foul_share = float((ev.type == "OF").sum() / n_to)

    # rebounds ----------------------------------------------------------------------------------
    usable = rb[rb.lineup_ok & ~rb.likely_dead]
    team_reb_share = float(usable.team_rebound.mean())
    ft_miss = usable[usable.prev_type == "FTA"]
    ft_orb = float((ft_miss.type == "O").mean()) if len(ft_miss) else 0.12
    orb_events = float((ev.type == "O").sum())
    p_putback = float((s.context == "putback").sum() / max(orb_events, 1))

    # time ---------------------------------------------------------------------------------------
    second = s[s.since_orb.notna() & (s.context != "putback")]
    time_samples = {
        "halfcourt": seconds_sample(first[first.context == "halfcourt"].poss_seconds, 8, 28),
        "transition": seconds_sample(first[first.context == "transition"].poss_seconds, 1, 7),
        "second": seconds_sample(second.since_orb, 3, 20),
        "putback": seconds_sample(s[s.context == "putback"].since_orb, 0, 4),
    }

    out = {
        "seasons": list(REFERENCE_SEASONS),
        "make_level": {z: round(v, 4) for z, v in level.items()},
        "make_delta": make_delta, "zone_mult": zone_mult,
        "p_transition": p_trans, "p_putback": round(p_putback, 4),
        "assisted": {c: {z: float(assisted[c][z]) for z in ZONES} for c in ("halfcourt", "transition", "putback")},
        "block_rate": {z: blocked[z] for z in ZONES},
        "p_shooting_foul": round(p_shooting_foul, 4), "three_share_of_trips": round(three_share_of_trips, 4),
        "p_non_shooting_foul": round(non_shooting / n_poss, 4), "p_and_one": round(and_one, 4),
        "steal_share": round(steal_share, 4), "off_foul_share": round(off_foul_share, 4),
        "team_rebound_share": round(team_reb_share, 4), "ft_orb": round(ft_orb, 4),
        "time": time_samples,
        "subs_per_team_game": round(float((ev.type == "IN").sum() / (2 * n_games)), 2),
        "timeouts_per_game": round(float((ev.type == "TOUT").sum() / n_games), 2),
        "rotation": rotation_templates(stints, pg),
    }
    CALIBRATION_FILE.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    res = calibrate()
    for k, v in res.items():
        if k not in ("time", "rotation"):
            print(f"{k:24s} {v}")
    print("bench minutes", round(sum(res["rotation"]["bench"]), 1), "starter minutes", round(sum(res["rotation"]["starter"]), 1))
