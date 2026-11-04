"""Validate the built tables. Exits with status 1 when a check fails.

    uv run python scripts/check_tables.py

Limits below reflect what the audit explained (see scripts/audit/foundation.py):
the official feed corrects a handful of box lines after the game, and two possessions
fall between the two rows of a same-second substitution and carry a lineup_ok flag.
"""

import sys

import pandas as pd

from bk.config import TABLES_DIR as T

KEY = ["season", "gamecode"]
PG = KEY + ["player_id"]
OFFICIAL_STATS = ["games", "pts", "fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta", "orb", "drb", "ast", "stl", "tov",
                  "blk", "blk_against", "pf", "fd"]
MAX_OFFICIAL_DIFF_CELLS = 40   # stat corrections after the game, out of about 15,000 cells
MAX_OFFICIAL_DIFF_SIZE = 2
MAX_NON_FIVE_LINEUPS = 2
MIN_BLOCK_LINK_RATE = 0.99
MIN_ROSTER_MINUTE_SHARE = 0.99
LOW_VOLUME_MIN_MINUTES = 100
LOW_VOLUME_INSIDE_FGA = 2.5  # per game
LOW_VOLUME_MAX_FINISHING = 16
LOW_TOUCHES_PER_GAME = 6
LOW_TOUCHES_MAX_BALL_SECURITY = 16
MINUTES_TOLERANCE = 1.0
MAX_STINT_OFF_PLAYER_GAMES = 10

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'OK  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")
    if not ok:
        failures.append(name)


sh = pd.read_parquet(T / "shots.parquet")
pg = pd.read_parquet(T / "player_games.parquet")
po = pd.read_parquet(T / "possessions.parquet")
st = pd.read_parquet(T / "stints.parquet")
ev = pd.read_parquet(T / "events.parquet")
games = pd.read_parquet(T / "games.parquet")
off = pd.read_parquet(T / "official_totals.parquet")
people = pd.read_parquet(T / "people.parquet")
rc = pd.read_parquet(T / "rebound_chances.parquet")

# official totals --------------------------------------------------------------
ours = pg.groupby(["season", "player_id"]).agg(
    games=("gamecode", "size"), **{c: (c, "sum") for c in OFFICIAL_STATS if c != "games"})
j = ours.join(off.set_index(["season", "player_id"]).add_suffix("_off"), how="outer")
check("official totals: same players", j.games.notna().all() and j.games_off.notna().all())
diffs = pd.concat([(j[c] - j[f"{c}_off"]).abs() for c in OFFICIAL_STATS])
check("official totals: stats", (diffs > 0).sum() <= MAX_OFFICIAL_DIFF_CELLS and diffs.max() <= MAX_OFFICIAL_DIFF_SIZE,
      f"{int((diffs > 0).sum())} differing cells, largest {diffs.max():.0f}")

# feed against box -------------------------------------------------------------
bx = pg.groupby(KEY)[["fg2a", "fg3a"]].sum()
fga = sh.groupby(KEY).size()
check("shots equal box FGA per game", ((bx.fg2a + bx.fg3a) == fga).all())
for stat, kinds in {"orb": ["O"], "drb": ["D"], "stl": ["ST"], "tov": ["TO"], "blk": ["FV"], "fd": ["RV"],
                    "fta": ["FTM", "FTA"], "ast": ["AS"]}.items():
    counts = ev[ev.type.isin(kinds) & (ev.player_id != "")].groupby(PG).size()
    box = pg.set_index(PG)[stat]
    keys = box.index.union(counts.index)
    bad = (box.reindex(keys).fillna(0) != counts.reindex(keys).fillna(0)).sum()
    check(f"events equal box {stat} per player-game", bad == 0, f"{bad} differ")

# scores -----------------------------------------------------------------------
pts = pg.groupby(KEY + ["team"]).pts.sum()
g = pd.concat([games[KEY + ["home", "home_score"]].set_axis(KEY + ["team", "score"], axis=1),
               games[KEY + ["away", "away_score"]].set_axis(KEY + ["team", "score"], axis=1)]).set_index(KEY + ["team"]).score
check("box points equal final score", (pts.reindex(g.index) == g).all())
pp = po.groupby(KEY + ["offense"]).points.sum()
pp.index.names = KEY + ["team"]
check("possession points equal final score", (pp.reindex(g.index) == g).all())

# lineups and minutes ----------------------------------------------------------
check("non-5 lineups stay flagged and rare", (~po.lineup_ok).sum() <= MAX_NON_FIVE_LINEUPS
      and ((po.off_lineup.map(len) != 5) | (po.def_lineup.map(len) != 5)).sum() == (~po.lineup_ok).sum(),
      f"{int((~po.lineup_ok).sum())} possessions")
periods = ev.groupby(KEY).period.max().rename("periods")
team = pg.groupby(KEY + ["team"]).minutes.sum().rename("mins").reset_index().join(periods, on=KEY)
team_gap = (team.mins - (200 + 25 * (team.periods - 4))).abs()
check("box team minutes match game length", (team_gap <= MINUTES_TOLERANCE).all(),
      f"{int((team_gap > MINUTES_TOLERANCE).sum())} team-games off")
box_minutes = pg.set_index(PG).minutes
stint_gap = (st.groupby(PG).seconds.sum().div(60).reindex(box_minutes.index).fillna(0) - box_minutes).abs()
check("stint minutes match box", (stint_gap > MINUTES_TOLERANCE).sum() <= MAX_STINT_OFF_PLAYER_GAMES,
      f"{int((stint_gap > MINUTES_TOLERANCE).sum())} player-games off by >1 min")

# derived tables ---------------------------------------------------------------
fv = (ev.type == "FV").sum()
rate = (sh.blocker_id != "").sum() / fv
check("blocks link to shots and blockers", rate >= MIN_BLOCK_LINK_RATE, f"{100 * rate:.1f}%")
check("rebound table covers every rebound", len(rc) == ev.type.isin(["O", "D"]).sum())
share = pg.merge(people, on=["season", "player_id"], how="left")
minute_share = share[share.height.notna()].minutes.sum() / share.minutes.sum()
check("height coverage", minute_share >= MIN_ROSTER_MINUTE_SHARE, f"{100 * minute_share:.1f}% of minutes")
check("position coverage", share.position.notna().all())

# ratings ---------------------------------------------------------------------
ratings = pd.read_parquet(T / "ratings_season.parquet")
inside = sh[sh.zone_group == "inside"].groupby(["season", "player_id"]).size().rename("inside_fga")
low = ratings.join(inside, on=["season", "player_id"]).fillna({"inside_fga": 0})
low = low[(low.minutes >= LOW_VOLUME_MIN_MINUTES) & (low.inside_fga / low.games <= LOW_VOLUME_INSIDE_FGA)]
check("low-volume finishers stay out of the top", (low.finishing <= LOW_VOLUME_MAX_FINISHING).all(),
      f"highest {int(low.finishing.max())} among {len(low)} player-seasons")
touches = pg.groupby(["season", "player_id"])[["fg2a", "fg3a", "fta", "tov", "ast"]].sum()
touches = (touches.fg2a + touches.fg3a + 0.44 * touches.fta + touches.tov + touches.ast).rename("touches")
quiet = ratings.join(touches, on=["season", "player_id"]).fillna({"touches": 0})
quiet = quiet[(quiet.minutes >= LOW_VOLUME_MIN_MINUTES) & (quiet.touches / quiet.games < LOW_TOUCHES_PER_GAME)]
check("low-touch players stay out of the top of ball security", (quiet.ball_security <= LOW_TOUCHES_MAX_BALL_SECURITY).all(),
      f"highest {int(quiet.ball_security.max())} among {len(quiet)} player-seasons")

print(f"\n{len(failures)} failed" if failures else "\nall checks passed")
sys.exit(1 if failures else 0)
