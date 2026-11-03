"""Simulation parameters.

Two kinds of numbers live here and the UI must say which is which:

* calibrated: fitted on EuroLeague play-by-play (see bk.sim.calibrate). These
  defaults are overwritten by data/tables/sim_calibration.json when present.
* prior: not observable in public data (open vs. contested, pull-up vs. catch).
  Values come from published NBA tracking splits and are exposed so a coach can
  tune them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from bk.config import TABLES_DIR

CALIBRATION_FILE = TABLES_DIR / "sim_calibration.json"


@dataclass
class SimParams:
    # --- priors: open vs contested (logit half-gap; open = +gap, contested = -gap) -------------
    # NBA tracking: catch-and-shoot 3 open ~39% vs contested ~34%; rim open ~70% vs contested ~58%
    contest_gap: dict[str, float] = field(default_factory=lambda: {
        "rim": 0.26, "paint": 0.18, "mid": 0.10, "corner3": 0.11, "above_break3": 0.11})
    # extra penalty for self-created (off-the-dribble) shots, scaled down by Şut Yaratma
    dribble_penalty: float = 0.15
    # how much one SD of defender rating moves contest probability (logit units)
    defender_contest_beta: float = 0.5
    # how much one SD of the matchup edge moves an option's weight (log units)
    option_edge_beta: float = 0.35

    # --- calibrated from data (defaults are placeholders until calibrate runs) --------------
    fatigue_per_min: float = -0.010     # logit change per stint minute beyond fatigue_free_min
    fatigue_free_min: float = 5.0
    clutch_league: float = -0.03        # league-wide logit shift in clutch time
    clutch_beta: float = 0.08           # per SD of the Clutch rating
    shooting_foul_rate: dict[str, float] = field(default_factory=lambda: {
        "rim": 0.16, "paint": 0.10, "mid": 0.03, "corner3": 0.015, "above_break3": 0.015})
    and_one_share: float = 0.22         # share of shooting fouls where the shot still counts
    orb_rate: float = 0.29              # league offensive rebound rate on missed FGs
    second_chance_ppp: float = 1.10     # points per putback/second-chance possession
    # prior: turnover rate per action kind before ball-security / steal adjustments, from
    # Synergy-style play-type turnover frequencies (PnR ball handler ~14%, post-up ~12%,
    # handoff ~6%). League turnovers per possession (~17%) also include transition and
    # pre-set turnovers, so sets are deliberately not forced to match it.
    turnover_rate: dict[str, float] = field(default_factory=lambda: {
        "screen": 0.01, "pass": 0.02, "handoff": 0.06, "drive": 0.14, "post": 0.12, "cut": 0.03})

    calibrated_keys: tuple[str, ...] = ()

    @classmethod
    def load(cls) -> "SimParams":
        p = cls()
        if CALIBRATION_FILE.exists():
            data = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
            for k, v in data.items():
                if hasattr(p, k):
                    setattr(p, k, v)
            p.calibrated_keys = tuple(data)
        return p

    def to_dict(self) -> dict:
        d = asdict(self)
        d["calibrated_keys"] = list(self.calibrated_keys)
        return d
