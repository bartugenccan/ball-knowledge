"""A full game played one possession at a time.

Each game keeps a real clock, score, team and personal fouls, five players per side and who has
been on court how long. A seed fixes every draw, so any one simulated game can be played again with
its full event list.

What the public data can support decides what an event may say. There is no defender assignment,
contest distance or play type, so events name who shot, from which zone and whether the shot was
assisted, blocked or fouled, and nothing about how the look was created.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from bk.match.calibrate import MINUTES
from bk.match.model import TeamModel

PERIOD_SECONDS = 600
OT_SECONDS = 300
GARBAGE_MARGIN = 20
BONUS_AT = 4            # the fifth team foul of a period starts the penalty
FOUL_OUT = 5
MAX_SWAPS = 3
CLOSE_MARGIN = 10

# box score columns
SEC, PTS, F2M, F2A, F3M, F3A, FTM, FTA, ORB, DRB, AST, STL, BLK, TOV, PF, FD, SELF = range(17)
BOX_COLS = ("sec", "pts", "f2m", "f2a", "f3m", "f3a", "ftm", "fta", "orb", "drb", "ast", "stl", "blk", "tov", "pf", "fd", "self")


@dataclass
class Tuning:
    """Settings chosen on the games of E2025 and rounds 1-9 of E2026, each change tested on its own
    (data/audit/match_candidates.md). Games after that are the new test."""
    home_make: float = 0.085         # logit added to the home side's shots
    away_foul: float = 1.04         # the away defense is called for slightly more fouls
    rim_coef: float = 0.05          # logit per unit of lineup rim effect (points per 100 possessions)
    three_coef: float = 0.026       # log change in three-point attempts per unit of lineup three effect (per 100 possessions)
    team_form_sd: float = 0.02      # one team's shooting night, logit
    player_form_sd: float = 0.08    # one player's shooting night, logit
    usage_sd: float = 0.3          # one player's share of the shots tonight, log
    minutes_form_sd: float = 0.45    # how much a player's share of the minutes moves from game to game, log
    night_make_sd: float = 0.025    # shooting conditions shared by both sides, logit
    timeout_chance: float = 0.03    # chance a coach calls time at a dead ball, apart from stopping a run
    game_pace_sd: float = 0.03      # the same tempo for both sides on a given night
    foul_night_sd: float = 0.10     # how tightly tonight's referees call the game
    ft_assist: float = 0.3          # share of shooting-foul trips that follow an assist in the box score
    lineup_block_level: float = 0.07
    lineup_trip_level: float = 17.0
    tempo_scale: float = 2.0        # how much of a team's tempo reaches the game
    transition_scale: float = 2.0
    transition_shift: float = 0.0   # logit, league-wide
    own_to_scale: float = 0.0
    own_foul_scale: float = 0.0
    orb_team_scale: float = 0.5
    mid_scale: float = 1.0
    closer_weight: float = 1.0      # weight of a player's record in close finishes, last five minutes
    team_strength: float = 0.25      # share of the team's points per 100 above the league added on top of its players
    usage_power: float = 1.2        # above 1, the shots lean further toward a lineup's main scorers
    shot_scale: float = 1.0
    three_make_shift: float = 0.0   # logit
    two_make_shift: float = 0.0     # logit
    recent_minutes: float = 0.5     # share of a player's last few games in the minutes he is expected to play
    max_centers: float = 2.0
    score_effect: float = -0.009    # make logit per point of lead: leaders ease off, teams behind push (scripts/match/score_effects.py)
    time_scale: float = 1.04
    to_scale: float = 1.0
    three_scale: float = 1.06
    orb_scale: float = 1.05
    shot_foul_scale: float = 1.08
    non_shot_foul_scale: float = 0.9
    eval_chance: float = 1.0        # chance a coach looks at the bench on a dead ball
    sub_stay: float = 1.0           # preference for whoever is already on court
    sub_behind: float = 0.5        # per minute behind his usual share of the game so far
    sub_tired: float = 0.45         # per minute past his usual stint
    sub_noise: float = 0.45
    sub_fresh: float = 2.5          # a player who just came in stays on
    sub_fresh_min: float = 2.5      # minutes
    fatigue_per_min: float = -0.0026
    fatigue_free_min: float = 5.0
    clutch: float = -0.0127


@dataclass
class Lineup:
    five: tuple[int, ...]
    shot_w: list[float]             # who takes the shot
    shot_pick: float
    shot_sum: float                 # how many shots this lineup takes
    tov_w: list[float]
    tov_sum: float
    trip_w: list[float]
    trip_sum: float
    fd_w: list[float]
    fd_sum: float
    orb_w: list[float]
    orb_sum: float
    drb_w: list[float]
    drb_sum: float
    ast_w: list[float]
    stl_w: list[float]
    blk_sum: float
    blk_w: list[float]
    rim: float
    three: float
    foul_w: list[float]


@dataclass
class Side:
    model: TeamModel
    index: int                      # 0 home, 1 away
    n: int = 0
    court: list[int] = field(default_factory=list)
    box: list[list[int | float]] = field(default_factory=list)
    parts: list[list[float]] = field(default_factory=list)   # seconds in each quarter, then in the last five minutes
    stint_start: list[float] = field(default_factory=list)
    left_at: list[float] = field(default_factory=list)
    fouls: list[int] = field(default_factory=list)
    pts: int = 0
    team_fouls: int = 0
    run: int = 0
    answered: int = 0               # the size of the opposing run a timeout already answered
    timeouts: int = 0
    form: float = 0.0
    p_form: list[float] = field(default_factory=list)
    u_form: list[float] = field(default_factory=list)
    tonight: list[float] = field(default_factory=list)   # minutes the coach has in mind for each player tonight
    lineups: dict = field(default_factory=dict)
    subs: int = 0
    poss: int = 0
    zones: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0, 0, 0, 0])  # inside/mid/corner/above: attempts then makes
    trans_shots: int = 0
    points_off_to: int = 0
    second_chance_pts: int = 0
    trans_pts: int = 0


Z_INDEX = {"inside": 0, "mid": 1, "corner3": 2, "above_break3": 3}
ZONE_VALUE = {"inside": 2, "mid": 2, "corner3": 3, "above_break3": 3}


def _choice(rng: random.Random, weights: list[float], total: float) -> int:
    r = rng.random() * total
    for i, w in enumerate(weights):
        r -= w
        if r < 0:
            return i
    return len(weights) - 1


class GameSim:
    def __init__(self, home: TeamModel, away: TeamModel, league: dict, tune: Tuning | None = None,
                 seed: int = 1, trace: bool = False, neutral: bool = False, expected_margin: float = 0.0):
        self.L, self.T = league, tune or Tuning()
        self.rng = random.Random(seed)
        self.coord_rng = random.Random(seed + 1)
        self.trace = trace
        self.events: list[dict] = []
        self.neutral = neutral
        self.expected_margin = expected_margin   # the home side's expected final margin before tip-off
        self.sides = [Side(home, 0), Side(away, 1)]
        self.elapsed = 0.0
        self.period = 1
        self.left = float(PERIOD_SECONDS)
        self.margins: list[float] = [0.0]  # home margin at the end of each game minute
        self.next_minute = 60.0
        self.lead_changes = 0
        self.ties = 0
        self.last_leader = 0
        self.max_lead = [0, 0]
        self.quarters: list[list[int]] = []
        self.best_run = [0, 0]
        self.t_hc = league["time"]["halfcourt"]
        self.t_tr = league["time"]["transition"]
        self.t_2nd = league["time"]["second"]
        self.t_pb = league["time"]["putback"]
        self.last_score_team = -1
        self.tv_done = False
        self.pace_night = math.exp(self.rng.gauss(0, self.T.game_pace_sd))
        self.foul_night = math.exp(self.rng.gauss(0, self.T.foul_night_sd))
        self.night_make = self.rng.gauss(0, self.T.night_make_sd)
        for s in self.sides:
            self._ready(s)

    # -- setup -------------------------------------------------------------------------
    def _ready(self, s: Side) -> None:
        players = s.model.players
        s.n = len(players)
        s.box = [[0] * len(BOX_COLS) for _ in players]
        s.parts = [[0.0] * 5 for _ in players]
        s.stint_start = [0.0] * s.n
        s.left_at = [-1000.0] * s.n
        s.fouls = [0] * s.n
        t, r = self.T, self.rng
        s.form = r.gauss(0, t.team_form_sd)
        s.p_form = [r.gauss(0, t.player_form_sd) for _ in players]
        s.u_form = [math.exp(r.gauss(0, t.usage_sd)) for _ in players]
        usual = [p.target if p.recent_minutes is None else (1 - t.recent_minutes) * p.target + t.recent_minutes * p.recent_minutes for p in players]
        raw = [m * math.exp(r.gauss(-t.minutes_form_sd ** 2 / 2, t.minutes_form_sd)) for m in usual]
        total = sum(raw) or 1.0
        s.tonight = [min(x * 200.0 / total, 40.0) for x in raw]

    def _lineup(self, s: Side) -> Lineup:
        key = tuple(sorted(s.court))
        got = s.lineups.get(key)
        if got is not None:
            return got
        ps = [s.model.players[i] for i in key]
        shot = [(p.rate["inside"] + p.rate["mid"] + p.rate["three"]) * s.u_form[i] for p, i in zip(ps, key)]
        pick = [x ** self.T.usage_power for x in shot] if self.T.usage_power != 1.0 else shot
        tov = [p.tov * s.u_form[i] for p, i in zip(ps, key)]
        trip = [p.trip for p in ps]
        fd = [p.fd for p in ps]
        orb = [p.orb for p in ps]
        drb = [p.drb for p in ps]
        blk = [p.blk for p in ps]
        lu = Lineup(key, pick, sum(pick), sum(shot), tov, sum(tov), trip, sum(trip), fd, sum(fd), orb, sum(orb), drb, sum(drb),
                    [p.ast for p in ps], [p.stl for p in ps], sum(blk), blk,
                    sum(p.rim_effect for p in ps), sum(p.three_effect for p in ps), [p.foul for p in ps])
        s.lineups[key] = lu
        return lu

    # -- clock ---------------------------------------------------------------------------
    def _advance(self, dt: float) -> None:
        dt = max(0.0, min(dt, self.left))
        self.left -= dt
        self.elapsed += dt
        part = min(self.period, 4) - 1
        late = self.period >= 4 and self.left <= 300
        for s in self.sides:
            for i in s.court:
                s.box[i][SEC] += dt
                s.parts[i][part] += dt
                if late:
                    s.parts[i][4] += dt
        margin = self.sides[0].pts - self.sides[1].pts
        while self.elapsed >= self.next_minute and len(self.margins) <= MINUTES:
            self.margins.append(float(margin))
            self.next_minute += 60.0

    def _clock(self) -> str:
        whole = int(math.ceil(self.left))
        return f"{whole // 60}:{whole % 60:02d}"

    def _log(self, event: str, side: Side | None, **data) -> None:
        if self.trace:
            self.events.append({"event": event, "period": self.period, "clock": self._clock(), "elapsed": round(self.elapsed, 1),
                                "team": side.model.code if side else None, "side": side.index if side else None,
                                "home": self.sides[0].pts, "away": self.sides[1].pts, **data})

    def _score(self, s: Side, pts: int) -> None:
        other = self.sides[1 - s.index]
        before = self.sides[0].pts - self.sides[1].pts
        s.pts += pts
        margin = self.sides[0].pts - self.sides[1].pts
        if margin == 0:
            self.ties += 1
        leader = 0 if margin > 0 else 1 if margin < 0 else -1
        if leader != -1:
            if self.last_leader != leader and self.last_leader in (0, 1) and before != margin:
                self.lead_changes += 1
            self.last_leader = leader
            lead = abs(margin)
            if lead > self.max_lead[leader]:
                self.max_lead[leader] = lead
        if self.last_score_team == s.index:
            s.run += pts
        else:
            s.run = pts
            other.run = 0
            other.answered = 0
        self.last_score_team = s.index
        if s.run > self.best_run[s.index]:
            self.best_run[s.index] = s.run

    # -- substitutions ---------------------------------------------------------------------
    def _trouble(self, s: Side, i: int) -> float:
        """How hard a coach protects a player in foul trouble."""
        f = s.fouls[i]
        if f >= FOUL_OUT:
            return 1000.0
        limit = {1: 2, 2: 3, 3: 4}.get(self.period, 5)
        if self.period >= 4:
            late = self.left <= 300
            return 1.2 if f == 4 and not late else 0.0
        return 2.5 if f >= limit else 0.0

    def _rate_players(self, s: Side) -> list[tuple[float, int]]:
        t, r = self.T, self.rng
        minute = min(int(self.elapsed // 60), MINUTES - 1)
        last_game = self.period >= 4 and self.left <= 300
        margin = abs(self.sides[0].pts - self.sides[1].pts)
        garbage = self.period >= 4 and self.left <= 240 and margin >= GARBAGE_MARGIN
        out: list[tuple[float, int]] = []
        share = min(self.elapsed / (MINUTES * 60), 1.0)
        short = s.n - sum(f >= FOUL_OUT for f in s.fouls) < 5
        for i, p in enumerate(s.model.players):
            if s.fouls[i] >= FOUL_OUT and not short:
                continue
            q = min(max(p.curve[minute], 0.01), 0.99)
            score = math.log(q / (1 - q))
            behind = s.tonight[i] * share - s.box[i][SEC] / 60
            score += t.sub_behind * behind
            on = i in s.court
            if on:
                score += t.sub_stay
                played = (self.elapsed - s.stint_start[i]) / 60
                over = played - p.stint
                if over > 0:
                    score -= t.sub_tired * over
                if played < t.sub_fresh_min:
                    score += t.sub_fresh
            elif self.elapsed - s.left_at[i] < 60:
                score -= 2.0
            score -= self._trouble(s, i)
            if last_game and not garbage:
                score += 0.05 * (p.target - 20)
                if t.closer_weight and margin <= CLOSE_MARGIN:
                    late = min(max(p.closer, 0.02), 0.98)
                    score += t.closer_weight * math.log(late / (1 - late))
            if garbage:
                score -= 0.12 * (p.target - 15)
            out.append((score + r.gauss(0, t.sub_noise), i))
        return out

    def _fit(self, s: Side, rated: list[tuple[float, int]]) -> list[int]:
        """The best five under a loose position rule: one center unless no one else fits, at most three guards."""
        players = s.model.players
        ordered = [i for _, i in sorted(rated, reverse=True)]
        chosen: list[int] = []
        centers = guards = 0
        for i in ordered:
            pos = players[i].position
            if (pos == "Center" and centers >= self.T.max_centers) or (pos == "Guard" and guards >= 3):
                continue
            chosen.append(i)
            centers += pos == "Center"
            guards += pos == "Guard"
            if len(chosen) == 5:
                break
        for i in ordered:
            if len(chosen) == 5:
                break
            if i not in chosen:
                chosen.append(i)
        if not any(players[i].position == "Guard" for i in chosen):
            guard = next((i for i in ordered if i not in chosen and players[i].position == "Guard"), None)
            if guard is not None:
                chosen[-1] = guard
        return chosen

    def _set_court(self, s: Side, five: list[int], reason: str = "") -> None:
        now = self.elapsed
        out = [i for i in s.court if i not in five]
        into = [i for i in five if i not in s.court]
        for i in out:
            s.left_at[i] = now
        for i in into:
            s.stint_start[i] = now
        if out and into:
            s.subs += len(into)
            if self.trace:
                players = s.model.players
                self._log("sub", s, into=[players[i].name for i in into], out=[players[i].name for i in out],
                          into_id=[players[i].player_id for i in into], out_id=[players[i].player_id for i in out], reason=reason)
        s.court = list(five)

    def _tv_timeout(self) -> None:
        """A long stop near the middle of a quarter: both benches get a look."""
        if self.period <= 4 and not self.tv_done and self.left <= 300:
            self.tv_done = True
            self._log("tv_timeout", None)
            for s in self.sides:
                self._set_court(s, self._fit(s, self._rate_players(s)))

    def _dead_ball(self) -> None:
        self._tv_timeout()
        for s in self.sides:
            if s.timeouts < 5 and self.rng.random() < self.T.timeout_chance:
                s.timeouts += 1
                self._log("timeout", s, run=0)
                self._set_court(s, self._fit(s, self._rate_players(s)))
                continue
            if self.rng.random() > self.T.eval_chance:
                must = any(s.fouls[i] >= FOUL_OUT for i in s.court)
                if not must:
                    continue
            rated = self._rate_players(s)
            five = self._fit(s, rated)
            gone = [i for i in s.court if i not in five]
            if len(gone) > MAX_SWAPS:
                # keep the on-court players the coach rates highest
                rank = {i: sc for sc, i in rated}
                keep = sorted(gone, key=lambda i: -rank.get(i, -99.0))[:len(gone) - MAX_SWAPS]
                newcomers = sorted((i for i in five if i not in s.court), key=lambda i: rank.get(i, -99.0))
                for out_going, back in zip(newcomers, keep):
                    five[five.index(out_going)] = back
                gone = [i for i in s.court if i not in five]
            reason = ""
            if any(s.fouls[i] >= FOUL_OUT for i in gone):
                reason = "foul_out"
            elif any(self._trouble(s, i) > 0 for i in gone):
                reason = "foul_trouble"
            self._set_court(s, five, reason)

    def _timeouts(self) -> None:
        """A coach stops a run. Timeouts have no measured effect on the next possessions, so only the story sees them."""
        for s in self.sides:
            other = self.sides[1 - s.index]
            if other.run >= 8 and other.run > s.answered and s.timeouts < 5 and self.last_score_team == other.index:
                if self.rng.random() < 0.5:
                    s.timeouts += 1
                    s.answered = other.run
                    self._log("timeout", s, run=other.run)
                    self._set_court(s, self._fit(s, self._rate_players(s)))

    # -- pieces of a possession ---------------------------------------------------------------
    def _draw_time(self, sample: list[float]) -> float:
        return sample[int(self.rng.random() * len(sample))]

    def _free_throws(self, off: Side, dfn: Side, i: int, n: int, reason: str) -> bool:
        """Returns True if the last shot missed and the ball is live."""
        p = off.model.players[i]
        missed_last = False
        made = 0
        for _ in range(n):
            off.box[i][FTA] += 1
            if self.rng.random() < p.ft:
                off.box[i][FTM] += 1
                off.box[i][PTS] += 1
                self._score(off, 1)
                made += 1
                missed_last = False
            else:
                missed_last = True
        self._log("ft", off, player=p.name, player_id=p.player_id, made=made, shots=n, reason=reason)
        return missed_last

    def _foul(self, dfn: Side, lu: Lineup) -> int:
        adj = []
        for w, j in zip(lu.foul_w, lu.five):
            # players in foul trouble foul less, the known caution of a player with four fouls
            adj.append(w * (0.55 if dfn.fouls[j] >= 3 else 1.0))
        k = lu.five[_choice(self.rng, adj, sum(adj))]
        dfn.fouls[k] += 1
        dfn.box[k][PF] += 1
        dfn.team_fouls += 1
        return k

    def _rebound(self, off: Side, dfn: Side, from_ft: bool) -> str:
        """Returns 'orb', 'drb' or 'dead'."""
        r = self.rng
        lo, ld = self._lineup(off), self._lineup(dfn)
        if from_ft:
            p_orb = self.L["ft_orb"] * (lo.orb_sum / max(lo.orb_sum + ld.drb_sum, 1e-6)) / 0.28
        else:
            p_orb = self.T.orb_scale * lo.orb_sum / max(lo.orb_sum + ld.drb_sum, 1e-6)
            if self.T.orb_team_scale:
                p_orb = min(max(p_orb, 0.02), 0.98)
                shift = self.T.orb_team_scale * (off.model.orb_off + dfn.model.orb_def)
                p_orb = 1 / (1 + math.exp(-(math.log(p_orb / (1 - p_orb)) + shift)))
        credited = r.random() >= self.L["team_rebound_share"]
        if r.random() < p_orb:
            if credited:
                i = lo.five[_choice(r, lo.orb_w, lo.orb_sum)]
                off.box[i][ORB] += 1
                self._log("orb", off, player=off.model.players[i].name, player_id=off.model.players[i].player_id)
            return "orb"
        if credited:
            i = ld.five[_choice(r, ld.drb_w, ld.drb_sum)]
            dfn.box[i][DRB] += 1
            self._log("drb", dfn, player=dfn.model.players[i].name, player_id=dfn.model.players[i].player_id)
        return "drb"

    def _shot(self, off: Side, dfn: Side, context: str, late_three: float = 1.0, heave: bool = False) -> tuple[str, int]:
        """Returns (result, shooter index). Result is 'make' or 'miss'."""
        r, T, L = self.rng, self.T, self.L
        lo, ld = self._lineup(off), self._lineup(dfn)
        i = lo.five[_choice(r, lo.shot_w, lo.shot_pick)]
        p = off.model.players[i]
        zd = dfn.model.zone_def
        w_in = p.rate["inside"] * zd["inside"]
        w_mid = T.mid_scale * p.rate["mid"] * zd["mid"]
        w_3 = T.three_scale * p.rate["three"] * zd["three"] * late_three * math.exp(-T.three_coef * (ld.three - dfn.model.three_mean))
        if context in L["zone_mult"]:
            zm = L["zone_mult"][context]
            w_in, w_mid, w_3 = w_in * zm["inside"], w_mid * zm["mid"], w_3 * zm["three"]
        pick = r.random() * (w_in + w_mid + w_3)
        if pick < w_in:
            zone = "inside"
        elif pick < w_in + w_mid:
            zone = "mid"
        else:
            zone = "corner3" if r.random() < p.corner_share else "above_break3"
        x = p.make[zone] + off.model.off_make[zone] + dfn.model.def_make[zone] + off.form + off.p_form[i] + self.night_make
        if context in L["make_delta"]:
            x += L["make_delta"][context][zone]
        if zone == "inside":
            x -= T.rim_coef * (ld.rim - dfn.model.rim_mean)
        x += T.three_make_shift if ZONE_VALUE[zone] == 3 else T.two_make_shift
        # one point per 100 possessions is about 0.02 logit on a league-average shot
        x += T.team_strength * 0.0195 * (off.model.net_off + dfn.model.net_def)
        if off.index == 0 and not self.neutral:
            x += T.home_make
        over = (self.elapsed - off.stint_start[i]) / 60 - T.fatigue_free_min
        if over > 0:
            x += T.fatigue_per_min * over
        if self.period >= 4 and self.left <= 300 and abs(off.pts - dfn.pts) <= 5:
            x += T.clutch
        # a lead only eases a team off once it is more than the matchup would predict by now
        expected = self.expected_margin * min(self.elapsed / 2400.0, 1.0)
        surprise = (off.pts - dfn.pts) - (expected if off.index == 0 else -expected)
        x += T.score_effect * max(-25.0, min(25.0, surprise))
        pm = 1 / (1 + math.exp(-x))
        if heave:
            pm = 0.05
        value = ZONE_VALUE[zone]
        fg_m, fg_a = (F3M, F3A) if value == 3 else (F2M, F2A)
        off.box[i][fg_a] += 1
        zi = Z_INDEX[zone]
        off.zones[zi] += 1
        if context == "transition":
            off.trans_shots += 1

        # a block is one way to miss, so more shot blockers do not lower the make rate twice
        blocker = None
        p_blk = L["block_rate"][zone] * (ld.blk_sum / T.lineup_block_level)
        if p_blk > 0 and r.random() < p_blk:
            blocker = ld.five[_choice(r, ld.blk_w, ld.blk_sum or 1.0)]
            dfn.box[blocker][BLK] += 1
            pm_after = 0.0
        else:
            pm_after = min(pm / max(1 - p_blk, 0.5), 0.98)

        coord = None
        if self.trace:
            pts = p.coords.get(zone)
            if pts:
                coord = pts[int(self.coord_rng.random() * len(pts))]

        if r.random() < pm_after:
            off.box[i][fg_m] += 1
            off.box[i][PTS] += value
            off.zones[zi + 4] += 1
            self._score(off, value)
            if context == "transition":
                off.trans_pts += value
            if context in ("putback", "second"):
                off.second_chance_pts += value
            # assist: less often for a shooter whose makes are less often assisted than the league's
            ctx = context if context in L["assisted"] else "halfcourt"
            p_ast = min(max(L["assisted"][ctx][zone] + p.self_share, 0.02), 0.98)
            passer = None
            if r.random() < p_ast:
                weights = [0.0 if j == i else w for w, j in zip(lo.ast_w, lo.five)]
                total = sum(weights)
                if total > 0:
                    passer = lo.five[_choice(r, weights, total)]
                    off.box[passer][AST] += 1
            if passer is None and context != "putback":
                off.box[i][SELF] += value
            self._log("make", off, player=p.name, player_id=p.player_id, zone=zone, value=value, context=context,
                      assist=off.model.players[passer].name if passer is not None else None,
                      assist_id=off.model.players[passer].player_id if passer is not None else None, coord=coord,
                      p_make=round(pm, 3))
            and_one = L["p_and_one"] * (lo.trip_w[lo.five.index(i)] / max(lo.trip_sum / 5, 1e-6))
            if zone == "inside":
                and_one *= 1.5
            elif value == 3:
                and_one *= 0.25
            if r.random() < and_one:
                k = self._foul(dfn, ld)
                off.box[i][FD] += 1
                self._log("foul", dfn, player=dfn.model.players[k].name, player_id=dfn.model.players[k].player_id,
                          drawn=p.name, fouls=dfn.fouls[k], kind="and_one")
                self._free_throws(off, dfn, i, 1, "and_one")
            return "make", i
        self._log("miss", off, player=p.name, player_id=p.player_id, zone=zone, value=value, context=context,
                  blocked_by=dfn.model.players[blocker].name if blocker is not None else None,
                  blocked_by_id=dfn.model.players[blocker].player_id if blocker is not None else None, coord=coord,
                  p_make=round(pm, 3))
        return "miss", i

    # -- one possession ---------------------------------------------------------------------
    def _possession(self, off: Side, dfn: Side, start: str) -> str:
        """Plays until the other side has the ball. Returns how the ball changed hands."""
        r, T, L = self.rng, self.T, self.L
        off.poss += 1
        chance = 0
        context = "halfcourt"
        p_tr = L["p_transition"].get(start, 0.04)
        x = math.log(p_tr / (1 - p_tr)) + T.transition_shift + T.transition_scale * (off.model.trans_off + dfn.model.trans_def)
        if r.random() < 1 / (1 + math.exp(-x)):
            context = "transition"
        late = self.period >= 4 and self.left <= 180
        margin = off.pts - dfn.pts
        while True:
            if self.left <= 0:
                return "period"
            lo, ld = self._lineup(off), self._lineup(dfn)
            # the trailing defense stops the clock late
            if self.period >= 4 and self.left <= 70 and 1 <= (off.pts - dfn.pts) <= 10 and r.random() < (0.45 if self.left > 30 else 0.8):
                self._advance(min(r.uniform(2.0, 7.0), self.left))
                if self.left <= 0:
                    return "period"
                k = self._foul(dfn, ld)
                drawn = lo.five[_choice(r, [w * off.model.players[j].ft for w, j in zip(lo.fd_w, lo.five)], lo.fd_sum)]
                off.box[drawn][FD] += 1
                self._log("foul", dfn, player=dfn.model.players[k].name, player_id=dfn.model.players[k].player_id,
                          drawn=off.model.players[drawn].name, fouls=dfn.fouls[k], kind="intentional")
                self._dead_ball()
                if dfn.team_fouls > BONUS_AT:
                    if self._free_throws(off, dfn, drawn, 2, "penalty"):
                        got = self._rebound(off, dfn, True)
                        if got == "orb":
                            chance += 1
                            context = "second"
                            continue
                        return "drb"
                    return "make"
                continue

            # a defensive foul away from the shot
            p_ns = L["p_non_shooting_foul"] * T.non_shot_foul_scale * dfn.model.def_foul * self.foul_night
            if off.index == 0 and not self.neutral:
                p_ns *= T.away_foul
            if r.random() < p_ns:
                self._advance(min(r.uniform(2.0, 16.0), self.left))
                if self.left <= 0:
                    return "period"
                k = self._foul(dfn, ld)
                drawn = lo.five[_choice(r, lo.fd_w, lo.fd_sum)]
                off.box[drawn][FD] += 1
                self._log("foul", dfn, player=dfn.model.players[k].name, player_id=dfn.model.players[k].player_id,
                          drawn=off.model.players[drawn].name, fouls=dfn.fouls[k],
                          kind="penalty" if dfn.team_fouls > BONUS_AT else "personal")
                self._dead_ball()
                if dfn.team_fouls > BONUS_AT:
                    if self._free_throws(off, dfn, drawn, 2, "penalty"):
                        got = self._rebound(off, dfn, True)
                        if got == "orb":
                            chance += 1
                            context = "second"
                            continue
                        return "drb"
                    return "make"
                context = "halfcourt" if context == "transition" else context
                continue

            # the chance ends in a turnover, a shot or a shooting foul
            forced = dfn.model.forced_to * T.to_scale * off.model.own_to ** T.own_to_scale
            weight_to = lo.tov_sum * forced
            weight_shot = lo.shot_sum * T.shot_scale
            weight_foul = L["p_shooting_foul"] * 100 * T.shot_foul_scale * dfn.model.def_foul * (lo.trip_sum / T.lineup_trip_level) * self.foul_night * off.model.own_foul ** T.own_foul_scale
            if off.index == 0 and not self.neutral:
                weight_foul *= T.away_foul
            total = weight_to + weight_shot + weight_foul
            pick = r.random() * total

            if context == "transition":
                seconds = self._draw_time(self.t_tr)
            elif context == "putback":
                seconds = self._draw_time(self.t_pb)
            elif context == "second":
                seconds = self._draw_time(self.t_2nd)
            else:
                seconds = self._draw_time(self.t_hc)
                seconds += T.tempo_scale * (off.model.pace_off + dfn.model.pace_def)
            seconds = max(1.0, seconds * T.time_scale * self.pace_night)
            if late:
                if margin < 0:
                    seconds *= 0.8
                elif margin > 0:
                    seconds *= 1.1

            # the last possession of a period is held for the final shot
            heave = False
            if self.left <= 26 and context == "halfcourt" and r.random() < 0.8:
                seconds = max(self.left - r.uniform(0.5, 4.0), 0.5)
            if seconds >= self.left:
                seconds = self.left
                if seconds < 2.5:
                    heave = r.random() < 0.5

            if pick < weight_to and not heave:
                self._advance(seconds * 0.75)
                if self.left <= 0:
                    return "period"
                i = lo.five[_choice(r, lo.tov_w, lo.tov_sum)]
                off.box[i][TOV] += 1
                name = off.model.players[i].name
                kind = r.random()
                if kind < L["steal_share"]:
                    k = ld.five[_choice(r, ld.stl_w, sum(ld.stl_w))]
                    dfn.box[k][STL] += 1
                    self._log("steal", dfn, player=dfn.model.players[k].name, player_id=dfn.model.players[k].player_id, lost_by=name, lost_by_id=off.model.players[i].player_id)
                    return "steal"
                if kind < L["steal_share"] + L["off_foul_share"]:
                    off.box[i][PF] += 1
                    off.fouls[i] += 1
                    off.team_fouls += 1
                    self._log("turnover", off, player=name, player_id=off.model.players[i].player_id, kind="offensive_foul", fouls=off.fouls[i])
                else:
                    self._log("turnover", off, player=name, player_id=off.model.players[i].player_id, kind="other")
                self._dead_ball()
                return "dead"

            self._advance(seconds)
            if pick < weight_to + weight_foul and not heave:
                # fouled on the shot, or stopped by the buzzer
                if self.left <= 0 and r.random() < 0.5:
                    return "period"
                i = lo.five[_choice(r, lo.trip_w, lo.trip_sum)]
                k = self._foul(dfn, ld)
                n = 3 if r.random() < L["three_share_of_trips"] * (off.model.players[i].rate["three"] / 8.0) else 2
                off.box[i][FD] += 1
                self._log("foul", dfn, player=dfn.model.players[k].name, player_id=dfn.model.players[k].player_id,
                          drawn=off.model.players[i].name, fouls=dfn.fouls[k], kind="shooting")
                if r.random() < T.ft_assist:
                    weights = [0.0 if j == i else w for w, j in zip(lo.ast_w, lo.five)]
                    total_w = sum(weights)
                    if total_w > 0:
                        off.box[lo.five[_choice(r, weights, total_w)]][AST] += 1
                self._dead_ball()
                if self._free_throws(off, dfn, i, n, "shooting"):
                    got = self._rebound(off, dfn, True)
                    if got == "orb":
                        chance += 1
                        context = "second"
                        continue
                    return "drb"
                return "make"

            late_three = 1.0
            if self.period >= 4 and self.left <= 150 and 3 <= (dfn.pts - off.pts) <= 12:
                late_three = 1.7
            result, _ = self._shot(off, dfn, context, late_three, heave)
            if result == "make":
                self._timeouts()
                self._tv_timeout()
                return "make"
            if self.left <= 0:
                return "period"
            got = self._rebound(off, dfn, False)
            if got == "orb":
                chance += 1
                context = "putback" if r.random() < L["p_putback"] else "second"
                continue
            return "drb"

    # -- whole game -----------------------------------------------------------------------
    def _start_period(self, period: int, first_off: int) -> None:
        self.period = period
        self.left = float(PERIOD_SECONDS if period <= 4 else OT_SECONDS)
        self.tv_done = False
        for s in self.sides:
            s.team_fouls = 0 if period <= 4 else s.team_fouls
            if period in (1, 3):
                five = [i for i, p in enumerate(s.model.players) if p.starter and s.fouls[i] < FOUL_OUT][:5]
                if len(five) < 5:
                    rated = sorted(self._rate_players(s), reverse=True)
                    for _, i in rated:
                        if i not in five:
                            five.append(i)
                        if len(five) == 5:
                            break
            else:
                five = self._fit(s, self._rate_players(s))
            self._set_court(s, five)
            for i in s.court:
                s.stint_start[i] = self.elapsed
        if self.trace:
            self._log("period_start", None, starters={s.model.code: [s.model.players[i].name for i in s.court] for s in self.sides},
                      starter_ids={s.model.code: [s.model.players[i].player_id for i in s.court] for s in self.sides})

    def _play_period(self, off: int) -> None:
        start = "period"
        while self.left > 0:
            a, b = self.sides[off], self.sides[1 - off]
            how = self._possession(a, b, start)
            if how == "period":
                break
            start = how
            off = 1 - off
        self.quarters.append([self.sides[0].pts, self.sides[1].pts])
        self._log("period_end", None)

    def play(self) -> "GameSim":
        for s in self.sides:
            s.court = []
        first = self.rng.randrange(2)
        self._start_period(1, first)
        self._play_period(first)
        self._start_period(2, 1 - first)
        self._play_period(1 - first)
        self._start_period(3, first)
        self._play_period(first)
        self._start_period(4, 1 - first)
        self._play_period(1 - first)
        period = 5
        while self.sides[0].pts == self.sides[1].pts and period < 9:
            who = self.rng.randrange(2)
            self._start_period(period, who)
            self._play_period(who)
            period += 1
        while len(self.margins) <= MINUTES:
            self.margins.append(float(self.sides[0].pts - self.sides[1].pts))
        return self
