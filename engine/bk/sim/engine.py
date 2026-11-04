"""Monte Carlo set simulator.

A set is a small decision tree:

    {
      "name": "Horns Flare",
      "start": "entry",
      "nodes": {
        "entry": {"type": "action", "kind": "screen", "ball": "1", "label": "5 perde 1'e",
                  "options": [
                    {"to": "pnr_drive", "weight": 0.5, "edge": {"off": ["1", "shot_creation"], "def": ["1", "perimeter_defense"]}},
                    {"to": "flare", "weight": 0.5}
                  ]},
        "flare": {"type": "shot", "shooter": "2", "zone": "above_break3", "creation": "catch", "openness": 0.6, "defender": "2"}
      }
    }

Slots "1".."5" are mapped to real players by the caller (offense) and to the
defenders guarding those slots (defense). Ratings drive branch probabilities,
turnovers, contest probability and make probability.
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from bk.sim.params import SimParams

AVG_RATING, RATING_SD = 11.5, 3.2
ZONE_PCT_KEY = {"rim": "rim_pct", "paint": "paint_pct", "mid": "mid_pct",
                "corner3": "corner3_pct", "above_break3": "three_pct"}


def _sig(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _sd(r: float) -> float:
    """Rating expressed in league SDs from average."""
    return (r - AVG_RATING) / RATING_SD


@dataclass
class Player:
    player_id: str
    name: str
    ratings: dict[str, int]                     # 1–20 attributes
    pct: dict[str, float]                       # shrunk shooting % per zone + ft_pct

    @classmethod
    def average(cls, name: str = "Ortalama oyuncu", pct: dict[str, float] | None = None) -> "Player":
        # defaults approximate EuroLeague 2025-26 league rates; profiles.league_average() uses real ones
        return cls("", name, {}, pct or {"rim_pct": .75, "paint_pct": .47, "mid_pct": .42,
                                         "corner3_pct": .37, "three_pct": .36, "ft_pct": .78})

    def r(self, key: str) -> float:
        return float(self.ratings.get(key, AVG_RATING))


@dataclass
class Context:
    stint_minutes: float = 4.0      # how long the offense has been on court (fatigue)
    clutch: bool = False            # last 5 min of Q4/OT within 5 points


@dataclass
class ShotOutcome:
    p_contest: float
    p_make_open: float
    p_make_contested: float
    p_foul: float


class SetSimulator:
    def __init__(self, set_def: dict, offense: dict[str, Player], defense: dict[str, Player],
                 params: SimParams | None = None, ctx: Context | None = None, seed: int = 7,
                 baseline: Player | None = None):
        self.s = set_def
        self.off, self.dfn = offense, defense
        self.p = params or SimParams.load()
        self.ctx = ctx or Context()
        self.rng = random.Random(seed)
        self.baseline = baseline or Player.average()  # league-average stand-in for sensitivity
        self._validate()

    # -- validation ------------------------------------------------------------
    def _validate(self) -> None:
        nodes = self.s.get("nodes", {})
        if self.s.get("start") not in nodes:
            raise ValueError("set 'start' must name a node")
        for nid, n in nodes.items():
            if n.get("type") == "action":
                if not n.get("options"):
                    raise ValueError(f"action node {nid!r} needs options")
                for o in n["options"]:
                    if o["to"] not in nodes:
                        raise ValueError(f"node {nid!r} points to unknown node {o['to']!r}")
            elif n.get("type") == "shot":
                if n.get("zone") not in ZONE_PCT_KEY:
                    raise ValueError(f"shot node {nid!r} has unknown zone {n.get('zone')!r}")
            else:
                raise ValueError(f"node {nid!r} has unknown type {n.get('type')!r}")

    # -- model pieces ------------------------------------------------------------
    def option_probs(self, node: dict) -> list[float]:
        ws = []
        for o in node["options"]:
            w = float(o.get("weight", 1.0))
            edge = o.get("edge")
            if edge:
                (os_, oa), (ds, da) = edge["off"], edge["def"]
                diff = _sd(self.off[os_].r(oa)) - _sd(self.dfn[ds].r(da))
                if o.get("favors") == "def":  # e.g. "defense blows up the set"
                    diff = -diff
                w *= math.exp(self.p.option_edge_beta * diff)
            ws.append(w)
        tot = sum(ws) or 1.0
        return [w / tot for w in ws]

    def turnover_prob(self, node: dict) -> float:
        base = self.p.turnover_rate.get(node.get("kind", "pass"), 0.02)
        handler = self.off[node.get("ball", "1")]
        defender = self.dfn[node.get("ball", "1")]
        return min(0.5, base * math.exp(-0.3 * _sd(handler.r("ball_security")) + 0.3 * _sd(defender.r("steals"))))

    def shot_model(self, node: dict) -> ShotOutcome:
        p = self.p
        zone = node["zone"]
        shooter = self.off[node["shooter"]]
        defender = self.dfn[node.get("defender", node["shooter"])]
        help_d = self.dfn[node["help"]] if node.get("help") else None
        is_inside = zone in ("rim", "paint")

        # contest probability: designed openness, pushed by the defender's rating
        d_attr = "rim_protection" if is_inside else "perimeter_defense"
        d_rating = defender.r(d_attr)
        if help_d is not None and is_inside:
            d_rating = max(d_rating, help_d.r("rim_protection"))
        openness = float(node.get("openness", 0.5))
        p_contest = _sig(_logit(1 - openness) + p.defender_contest_beta * _sd(d_rating))

        # make probability: shooter's zone skill is the average over open+contested looks
        base = _logit(shooter.pct.get(ZONE_PCT_KEY[zone], Player.average().pct[ZONE_PCT_KEY[zone]]))
        gap = p.contest_gap[zone]
        creation = _sd(shooter.r("shot_creation"))
        contested_gap = gap * max(0.3, 1 - 0.25 * creation)  # creators lose less when contested
        adj = 0.0
        if node.get("creation") == "dribble":
            adj -= p.dribble_penalty * max(0.0, 1 - 0.5 * creation)
        over = max(0.0, self.ctx.stint_minutes - p.fatigue_free_min)
        # league-wide effects only: the data show no lasting player differences in either
        adj += p.fatigue_per_min * over
        if self.ctx.clutch:
            adj += p.clutch_league
        p_open = _sig(base + gap + adj)
        p_cont = _sig(base - contested_gap + adj)
        p_foul = min(0.5, p.shooting_foul_rate[zone] * math.exp(0.25 * _sd(shooter.r("drawing_fouls"))))
        return ShotOutcome(p_contest, p_open, p_cont, p_foul)

    def orb_prob(self) -> float:
        o = sum(_sd(pl.r("off_rebounding")) for pl in self.off.values()) / max(len(self.off), 1)
        d = sum(_sd(pl.r("def_rebounding")) for pl in self.dfn.values()) / max(len(self.dfn), 1)
        return _sig(_logit(self.p.orb_rate) + 0.3 * (o - d))

    # -- one possession --------------------------------------------------------------
    def _free_throws(self, shooter: Player, n: int) -> int:
        ft = shooter.pct.get("ft_pct", 0.78)
        return sum(self.rng.random() < ft for _ in range(n))

    def run_once(self) -> tuple[int, list[str], str]:
        """Returns (points, path of node ids, terminal event)."""
        nodes = self.s["nodes"]
        nid, path = self.s["start"], []
        for _ in range(50):  # guard against cycles
            path.append(nid)
            node = nodes[nid]
            if node["type"] == "action":
                if self.rng.random() < self.turnover_prob(node):
                    return 0, path, "turnover"
                probs = self.option_probs(node)
                nid = self.rng.choices([o["to"] for o in node["options"]], probs)[0]
                continue
            # shot
            so = self.shot_model(node)
            shooter = self.off[node["shooter"]]
            value = 3 if node["zone"] in ("corner3", "above_break3") else 2
            contested = self.rng.random() < so.p_contest
            p_make = so.p_make_contested if contested else so.p_make_open
            tag = "contested" if contested else "open"
            if self.rng.random() < so.p_foul:
                if self.rng.random() < self.p.and_one_share:
                    return value + self._free_throws(shooter, 1), path, f"and_one_{tag}"
                return self._free_throws(shooter, value), path, f"fouled_{tag}"
            if self.rng.random() < p_make:
                return value, path, f"make_{tag}"
            if self.rng.random() < self.orb_prob():
                pts = 2 if self.rng.random() < self.p.second_chance_ppp / 2 else 0
                return pts, path, f"miss_{tag}_orb"
            return 0, path, f"miss_{tag}"
        raise RuntimeError("set has a cycle")

    # -- Monte Carlo ------------------------------------------------------------------
    def simulate(self, n: int = 10_000) -> dict:
        pts_dist: Counter = Counter()
        paths: Counter = Counter()
        terminal: dict[str, Counter] = defaultdict(Counter)
        total = 0
        for _ in range(n):
            pts, path, event = self.run_once()
            total += pts
            pts_dist[pts] += 1
            paths[" → ".join(path)] += 1
            terminal[path[-1]][event] += 1
            terminal[path[-1]]["_points"] += pts
        nodes = self.s["nodes"]
        shots = {}
        for nid, node in nodes.items():
            if node["type"] != "shot":
                continue
            so = self.shot_model(node)
            c = terminal.get(nid, Counter())
            reached = sum(v for k, v in c.items() if k != "_points")
            shots[nid] = {
                "label": node.get("label", nid), "shooter": self.off[node["shooter"]].name,
                "zone": node["zone"], "reach_rate": reached / n,
                "p_contest": round(so.p_contest, 3), "p_make_open": round(so.p_make_open, 3),
                "p_make_contested": round(so.p_make_contested, 3), "p_foul": round(so.p_foul, 3),
                "expected_fg": round(so.p_contest * so.p_make_contested + (1 - so.p_contest) * so.p_make_open, 3),
                "ppp_when_reached": round(c["_points"] / reached, 3) if reached else None,
            }
        actions = {}
        for nid, node in nodes.items():
            if node["type"] == "action":
                probs = self.option_probs(node)
                actions[nid] = {"label": node.get("label", nid), "turnover_prob": round(self.turnover_prob(node), 3),
                                "options": [{"to": o["to"], "prob": round(p_, 3)} for o, p_ in zip(node["options"], probs)]}
        events = Counter()
        for c in terminal.values():
            for k, v in c.items():
                if k != "_points":
                    events[k] += v
        return {
            "name": self.s.get("name", ""), "iterations": n, "ppp": round(total / n, 3),
            "points_distribution": {str(k): round(v / n, 4) for k, v in sorted(pts_dist.items())},
            "turnover_rate": round(events["turnover"] / n, 4),
            "events": {k: round(v / n, 4) for k, v in events.most_common()},
            "top_paths": [{"path": p_, "share": round(v / n, 4)} for p_, v in paths.most_common(6)],
            "shots": shots, "actions": actions,
        }

    def sensitivity(self, n: int = 4000) -> list[dict]:
        """PPP lost if each offensive player were replaced by a league-average player."""
        base = SetSimulator(self.s, self.off, self.dfn, self.p, self.ctx, seed=11).simulate(n)["ppp"]
        out = []
        for slot, pl in self.off.items():
            off2 = dict(self.off)
            off2[slot] = self.baseline
            ppp = SetSimulator(self.s, off2, self.dfn, self.p, self.ctx, seed=11).simulate(n)["ppp"]
            out.append({"slot": slot, "player": pl.name, "ppp_contribution": round(base - ppp, 3)})
        return sorted(out, key=lambda x: -x["ppp_contribution"])
