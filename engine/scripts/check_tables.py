"""Sanity checks for the built tables against the official box scores."""

import pandas as pd

from bk.config import TABLES_DIR as T

sh = pd.read_parquet(T / "shots.parquet")
pg = pd.read_parquet(T / "player_games.parquet")
po = pd.read_parquet(T / "possessions.parquet")
st = pd.read_parquet(T / "stints.parquet")
key = ["season", "gamecode"]
print("games:", pg[key].drop_duplicates().shape[0])
print("def lineup size (shots):", sh.def_lineup.apply(len).value_counts().to_dict())
print("off lineup size (poss):", po.off_lineup.apply(len).value_counts().to_dict())

m = st.groupby(key + ["player_id"]).seconds.sum().div(60).rename("stint_min")
j = pg.set_index(key + ["player_id"]).join(m)
j["diff"] = (j.stint_min - j.minutes).abs()
print("stint minutes vs box: median diff %.2f, >1 min: %d / %d" % (j["diff"].median(), (j["diff"] > 1).sum(), len(j)))

bx = pg.groupby(key)[["fg2a", "fg3a", "ast"]].sum()
s2 = sh.groupby(key).agg(fga=("made", "size"), ast=("assisted", "sum"))
print("FGA mismatch games:", int(((bx.fg2a + bx.fg3a) != s2.fga).sum()),
      " AST mismatch games:", int((bx.ast != s2.ast).sum()))
print("shots with coords:", round(sh.x.notna().mean(), 3))

tm = pg.groupby(key + ["team"]).agg(f2=("fg2a", "sum"), f3=("fg3a", "sum"), orb=("orb", "sum"),
                                     tov=("tov", "sum"), fta=("fta", "sum"))
tm["formula"] = tm.f2 + tm.f3 - tm.orb + tm.tov + 0.44 * tm.fta
pc = po.groupby(key + ["offense"]).size().rename("events")
pc.index.names = key + ["team"]
c = tm.join(pc)
c["d"] = c.events - c.formula
print("possessions (events) vs formula: mean %.2f, |d| median %.2f, |d|<=2: %.0f%%, |d|<=4: %.0f%%"
      % (c.d.mean(), c.d.abs().median(), 100 * (c.d.abs() <= 2).mean(), 100 * (c.d.abs() <= 4).mean()))
print("points per possession:", round(po.points.sum() / len(po), 3))
print("zone counts:", sh.zone.value_counts().to_dict())
print("zone FG%:", sh.groupby("zone").made.mean().round(3).to_dict())
print("assisted share of makes by zone:", sh[sh.made].groupby("zone").assisted.mean().round(2).to_dict())
