import numpy as np
import pandas as pd

from bk.ratings.attributes import ATTRIBUTES, score
from bk.ratings.metrics import _shrink_prop


def test_shrinkage_pulls_small_samples_to_prior():
    small = _shrink_prop(pd.Series([3]), pd.Series([3]), 0.36, 100).iloc[0]
    big = _shrink_prop(pd.Series([450]), pd.Series([1000]), 0.36, 100).iloc[0]
    assert 0.36 < small < 0.39       # 3/3 barely moves the needle
    assert 0.43 < big < 0.45         # 45% on 1000 attempts mostly survives


def _fake_metrics(n=200, seed=0):
    rng = np.random.default_rng(seed)
    cols = {c for a in ATTRIBUTES for c, _, _ in a.components}
    m = pd.DataFrame({c: rng.normal(size=n) for c in cols})
    for c in cols:
        m[f"n_{c}"] = rng.integers(0, 500, size=n)
    return m


def test_ratings_are_in_range_and_centered():
    m = _fake_metrics()
    r = score(m, m)
    for a in ATTRIBUTES:
        assert r[a.key].between(1, 20).all()
        assert 10.5 <= r[a.key].mean() <= 12.5
        assert r[f"{a.key}_conf"].between(0, 1).all()


def test_lower_is_better_components_invert():
    m = _fake_metrics()
    m["tov_pct"] = np.linspace(0, 1, len(m))
    r = score(m, m)
    assert r.ball_security.iloc[0] > r.ball_security.iloc[-1]
