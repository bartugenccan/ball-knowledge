"""Does the score change how teams play? Measured on the reference seasons, net of team strength.

    uv run python scripts/match/score_effects.py

Output feeds Tuning.score_effect in bk.match.sim. E2026 takes no part.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from bk.ratings.method import REFERENCE_SEASONS  # noqa: E402
from bk.ratings.metrics_v2 import load_tables  # noqa: E402

BINS = [-99, -20, -15, -10, -5, -2, 2, 5, 10, 15, 20, 99]
LABELS = ["<=-20", "-19..-15", "-14..-10", "-9..-5", "-4..-2", "-1..+1", "+2..+4", "+5..+9", "+10..+14", "+15..+19", ">=+20"]


def possessions_with_margin(t) -> pd.DataFrame:
    """Each possession with the offense's lead at its start and how strong both sides are overall."""
    po = t.possessions[t.possessions.season.isin(REFERENCE_SEASONS) & t.possessions.time_ok].copy()
    ev = t.events[t.events.season.isin(REFERENCE_SEASONS) & t.events.type.isin(["2FGM", "3FGM", "FTM"])]
    home = pd.read_parquet("../data/tables/games.parquet", columns=["season", "gamecode", "home"])
    po = po.merge(home, on=["season", "gamecode"])
    scores = ev[["season", "gamecode", "elapsed", "home_score", "away_score"]].astype({"elapsed": float}).sort_values("elapsed")
    po = po.astype({"start": float}).sort_values("start")
    merged = pd.merge_asof(po, scores, left_on="start", right_on="elapsed", by=["season", "gamecode"], direction="backward")
    merged[["home_score", "away_score"]] = merged[["home_score", "away_score"]].fillna(0)
    lead = merged.home_score - merged.away_score
    merged["lead"] = np.where(merged.offense == merged.home, lead, -lead)
    # team strength net of the game itself is too fine for this; a season average is enough to remove who leads
    merged["off_avg"] = merged.groupby(["season", "offense"]).points.transform("mean")
    merged["def_avg"] = merged.groupby(["season", "defense"]).points.transform("mean")
    merged["league"] = merged.groupby("season").points.transform("mean")
    merged["expected"] = merged.off_avg + merged.def_avg - merged.league
    merged["gap"] = merged.points - merged.expected
    return merged


def main() -> None:
    t = load_tables()
    d = possessions_with_margin(t)
    d["bin"] = pd.cut(d.lead, BINS, labels=LABELS)
    print("all periods: points per possession vs team average")
    print(d.groupby("bin", observed=True).agg(n=("gap", "size"), raw=("points", "mean"), gap=("gap", "mean"), se=("gap", "sem")).round(3).to_string())
    for label, part in (("Q1-Q3", d[d.period <= 3]), ("Q4 and OT", d[d.period >= 4])):
        x = part.lead.clip(-20, 20).to_numpy(dtype=float)
        y = part.gap.to_numpy()
        slope = float(np.polyfit(x, y, 1)[0])
        print(f"{label}: slope {slope * 10:+.4f} points per possession per 10 points of lead (n={len(part):,})")
    # what makes the difference?
    s = t.shots[t.shots.season.isin(REFERENCE_SEASONS)]
    s = s[s.zone_group.isin(("inside", "mid", "corner3", "above_break3"))].copy()
    s["lead"] = s.margin_before.clip(-20, 20)
    s["three"] = s.value == 3
    print("make rate vs lead:", s.groupby(pd.cut(s.lead, [-21, -10, -5, -1, 1, 5, 10, 20]), observed=True).made.mean().round(3).to_dict())
    print("three share vs lead:", s.groupby(pd.cut(s.lead, [-21, -10, -5, -1, 1, 5, 10, 20]), observed=True).three.mean().round(3).to_dict())
    print("transition share vs lead:", s.groupby(pd.cut(s.lead, [-21, -10, -5, -1, 1, 5, 10, 20]), observed=True).context.apply(lambda c: (c == "transition").mean()).round(3).to_dict())



if __name__ == "__main__":
    main()
