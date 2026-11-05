import pandas as pd
import pytest

from bk.config import TABLES_DIR
from bk.team.style import BY_KEY, METRICS, Metric, describe, rate

pytestmark = pytest.mark.skipif(not (TABLES_DIR / "shots.parquet").exists(), reason="tables not built")


def row(key: str, rank: int, stable: bool = True, value: float = 40.0) -> dict:
    return {"key": key, "rank": rank, "teams": 20, "stable": stable, "value": value, "league": 38.0, "z": 2.0 if rank <= 10 else -2.0}


def test_only_stable_tendencies_earn_a_sentence():
    assert describe([row("three_share", 1, stable=False)]) == []
    assert len(describe([row("three_share", 1, stable=True)])) == 1


def test_only_the_extremes_earn_a_sentence():
    assert describe([row("three_share", 10)]) == []
    assert "en yüksek" in describe([row("three_share", 2)])[0]
    assert "en düşük" in describe([row("three_share", 20)])[0]


def test_low_rank_reads_as_the_low_phrase():
    sentence = describe([row("transition", 19)])[0]
    assert BY_KEY["transition"].low in sentence


def test_rate_ignores_empty_denominators():
    m = Metric("x", "x", "tempo", "a", "b")
    out = rate(pd.DataFrame({"a": [1.0, 1.0], "b": [2.0, 0.0]}), m)
    assert out.iloc[0] == 50.0
    assert pd.isna(out.iloc[1])


def test_counts_match_the_box_score():
    from bk.ratings.metrics_v2 import load_tables
    from bk.team.style import team_game_counts
    t = load_tables()
    counts = team_game_counts(t)
    assert set(m.num for m in METRICS) | set(m.den for m in METRICS) <= set(counts.columns)
    assert ((counts.threes <= counts.shots) & (counts.corners <= counts.threes) & (counts.assisted <= counts.makes)).all()
    pg = t.player_games.groupby(["season", "gamecode", "team"]).fta.sum().reset_index()
    merged = counts.merge(pg, on=["season", "gamecode", "team"], suffixes=("", "_b"))
    assert (merged.fta == merged.fta_b).all()
    # one side's offensive rebound chances are the other's defensive ones
    other = counts[["season", "gamecode", "team", "drb_chances"]].rename(columns={"team": "team_o", "drb_chances": "their_drb_chances"})
    a = counts.merge(other, on=["season", "gamecode", "team_o"])
    assert len(a) == len(counts)
    assert (a.orb_chances == a.their_drb_chances).all()
