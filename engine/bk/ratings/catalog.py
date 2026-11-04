"""The attributes the product shows, and how each one is presented."""

from __future__ import annotations

from bk.ratings.attributes import Attribute
from bk.ratings.defense import DEFENSE_ATTRIBUTES, DEFENSE_K
from bk.ratings.mental import MENTAL_ATTRIBUTES, MENTAL_SPECS
from bk.ratings.metrics_v2 import ATTRIBUTES_V2, INFO_METRICS, SPECS, TIER_ATTRIBUTES

ORDER = ("finishing", "mid_range", "three_point", "free_throw", "shot_creation", "passing", "ball_security", "drawing_fouls",
         "off_rebounding", "def_rebounding", "steals", "shot_blocking", "rim_protection", "perimeter_defense", "discipline",
         "team_defense", "stamina", "consistency")

_ALL = {a.key: a for a in (*ATTRIBUTES_V2, *DEFENSE_ATTRIBUTES, *MENTAL_ATTRIBUTES)}
RATING_ATTRIBUTES: tuple[Attribute, ...] = tuple(_ALL[k] for k in ORDER)
ATTR_BY_KEY = {a.key: a for a in RATING_ATTRIBUTES}

PRIOR_K: dict[str, float] = {
    **{m: s.k for m, s in SPECS.items() if m not in INFO_METRICS},
    **DEFENSE_K,
    **{m: s.k for m, s in MENTAL_SPECS.items()},
}


def display_kind(key: str) -> str:
    return "tier" if key in TIER_ATTRIBUTES else "number"
