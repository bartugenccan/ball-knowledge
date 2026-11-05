"""New metric definitions, built side by side with the current ratings.

Every metric is a count over a clear opportunity (successes / trials) per player. Each one is
then shrunk toward the league, or toward the player's role when height and position proved to
help, optionally pooling earlier seasons. Parameters come from out-of-sample tests in
scripts/audit/stage3.py; E2026 never takes part in choosing them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from bk.config import TABLES_DIR
from bk.ratings.attributes import Attribute
from bk.ratings.method import REFERENCE_SEASONS, center_on_league, fixed_reference

FT_WEIGHT = 0.44
FOUL_WEIGHTS = {"personal": 1.0, "offensive": 1.0, "unsportsmanlike": 2.0, "technical": 2.0, "disqualifying": 2.0}
DRAWN_KINDS = ("personal", "unsportsmanlike", "disqualifying")  # offensive fouls are drawn on defense
TRIP_EXCLUDED = ("technical", "unsportsmanlike")
TWO_BACK_FACTOR = 0.5
HEIGHT_CENTER = 200.0
RELATIVE_METRICS = ("three_pct", "mid_pct", "inside_adj", "corner3_pct")  # also fed to the simulator
NON_SHOOTER_ATTEMPTS = 30   # with past seasons, and
NON_SHOOTER_RATE = 1.0      # attempts per 100 own possessions in this window
MID_NON_SHOOTER_PER_GAME = 0.5
FT_SKILL_PRIOR = 40.0       # free-throw skill used inside other priors
THREE_BASE_PCT = 0.32       # the three-point rating counts points above a shooter this good. The audit in
                            # scripts/audit/three_value.py compares this with other bases and with a plain weighting
THREE_ATTEMPT_PRIOR_GAMES = 2.0  # made-up games at his usual volume, so one hot night does not move the rating


@dataclass(frozen=True)
class Spec:
    kind: str                # "prop" (share of trials), "rate" (events per trial) or "resid" (signed value per trial)
    k: float                 # prior strength, in trials
    role: bool = False       # shrink toward the role (height, position) instead of the league
    carry: float = 0.0       # weight of last season's counts; two seasons ago gets half of that
    dispersion: float = 1.0  # variance of one trial over the plain binomial or Poisson variance
    scale: float = 1.0       # display units: 100 for "per 100 possessions"
    ft_prior: bool = False   # the role prior also uses the player's free-throw skill
    prior_from: str | None = None  # shrink toward the player's estimate on this metric instead


# k, role and carry come from scripts/audit/stage3.py. Dispersion is set so that 80% intervals
# hold about 80% of second-half results.
SPECS: dict[str, Spec] = {
    "ft_pct": Spec("prop", 40, role=True, carry=1.0, dispersion=1.2),
    "stl_rate": Spec("rate", 600, carry=1.0, scale=100),
    "blk_share": Spec("prop", 40, role=True, carry=0.5),
    "foul_rate": Spec("rate", 600, role=True, carry=0.25, scale=100, dispersion=1.1),
    "orb_share": Spec("prop", 200, role=True, carry=1.0, dispersion=1.25),
    "drb_share": Spec("prop", 200, role=True, carry=0.5),
    "tov_share": Spec("prop", 200, role=True, carry=0.5),
    # how much a player has the ball: no role prior, or a low-touch player's use gets pulled up
    "usage_rate": Spec("rate", 40, carry=0.25, scale=100),
    "fd_rate": Spec("rate", 120, role=True, carry=0.25, scale=100, dispersion=1.5),
    "trip_rate": Spec("rate", 200, carry=0.25, scale=100, dispersion=1.5),
    "creation_rate": Spec("rate", 120, role=True, carry=0.5, scale=100, dispersion=2.8),
    "ast_share": Spec("prop", 40, role=True, carry=0.25, dispersion=1.5),
    "created_rate": Spec("rate", 150, role=True, carry=0.25, scale=100, dispersion=2.6),
    "three_pct": Spec("prop", 400, role=True, ft_prior=True, carry=1.0),
    "three_rate": Spec("rate", 80, role=True, carry=0.25, scale=100),
    # the within-season test picks k=80, but k=80 predicts next season worse than the league
    # average; k=300 is the season-ahead best. A rating should describe lasting ability.
    "mid_pct": Spec("prop", 300, role=True, ft_prior=True),
    "mid_rate": Spec("rate", 200, carry=0.25, scale=100),
    "inside_adj": Spec("prop", 150, role=True, carry=1.0),
    # how much a player finishes, not how well: no role prior, or a big man's low volume gets pulled up
    "inside_rate": Spec("rate", 30, carry=0.25, scale=100),
    # the selection rule gives k=120, which lifts low-volume players to 17; k=80 keeps them at 16 or
    # below and loses almost nothing (out-of-sample gain 68.4 against 68.5)
    "inside_self_rate": Spec("rate", 80, carry=1.0, scale=100),
    "corner3_pct": Spec("prop", 8000, prior_from="three_pct"),
    "opp_three_pct": Spec("prop", 2000),  # defenders barely control this, hence the very strong prior
}

# Built from other metrics rather than counted directly.
DERIVED_METRICS = ("three_value",)

# Shown as Low / Medium / High, not 1-20: the data cannot support finer steps.
TIER_ATTRIBUTES = {"mid_range", "perimeter_defense"}
CONSISTENCY_MIN_GAMES = 20  # game-to-game swing cannot be judged from fewer games, whatever the correction
TIER_LOW_MAX, TIER_MEDIUM_MAX = 9, 13  # the middle band is the league average +/- about half an SD

# Reported on the card but not rated: the data show no stable corner skill apart from overall shooting.
INFO_METRICS = ("corner3_pct",)

ATTRIBUTES_V2: tuple[Attribute, ...] = (
    Attribute("free_throw", "Serbest Atış", "hucum", "veri", (("ft_pct", 1, 1),), "Serbest atış yüzdesi"),
    Attribute("steals", "Top Çalma", "savunma", "veri", (("stl_rate", 1, 1),), "Top çalma / 100 savunma"),
    Attribute("shot_blocking", "Blok", "savunma", "veri", (("blk_share", 1, 1),),
              "Sahadayken rakibin 2 sayılık denemelerinden blokladığı pay"),
    Attribute("discipline", "Faul Disiplini", "savunma", "veri", (("foul_rate", 1, -1),),
              "Faul / 100 hücum; sportmenlik dışı, teknik ve diskalifiye faulleri iki kat"),
    Attribute("off_rebounding", "Hücum Ribaundu", "hucum", "veri", (("orb_share", 1, 1),),
              "Sahadayken takımının hücum ribaund fırsatlarından aldığı pay"),
    Attribute("def_rebounding", "Savunma Ribaundu", "savunma", "veri", (("drb_share", 1, 1),),
              "Sahadayken takımının savunma ribaund fırsatlarından aldığı pay"),
    Attribute("ball_security", "Top Güvenliği", "hucum", "turetilmis", (("tov_share", .5, -1), ("usage_rate", .5, 1)),
              "Az top kaybı ve çok top kullanımı birlikte: top kaybı / top teması ve top teması / 100 hücum"),
    Attribute("drawing_fouls", "Faul Alma", "hucum", "turetilmis", (("fd_rate", .5, 1), ("trip_rate", .5, 1)),
              "Alınan faul ve serbest atış serisi / 100 hücum"),
    Attribute("shot_creation", "Şut Yaratma", "hucum", "turetilmis", (("creation_rate", 1, 1),),
              "Asistsiz sayı / 100 hücum; putback ve umut atışı hariç"),
    Attribute("passing", "Pas", "hucum", "turetilmis", (("ast_share", .6, 1), ("created_rate", .4, 1)),
              "Asist payı ve asistle yaratılan sayı / 100 hücum"),
    Attribute("three_point", "Üçlük", "hucum", "turetilmis", (("three_value", 1, 1),),
              "Sıradan bir şutçuya göre üçlükten maç başına fazladan üretilen sayı: 3 × deneme × (isabet − %32); umut atışı hariç"),
    Attribute("mid_range", "Orta Mesafe", "hucum", "turetilmis", (("mid_pct", .8, 1), ("mid_rate", .2, 1)),
              "Orta mesafe isabeti ve denemesi / 100 hücum"),
    Attribute("finishing", "Bitiricilik", "hucum", "turetilmis",
              (("inside_adj", .4, 1), ("inside_rate", .4, 1), ("inside_self_rate", .2, 1)),
              "Pota ve boyalı alanda isabet, deneme sayısı ve asistsiz isabet / 100 hücum; az şutla yüksek yüzde tek başına yetmez"),
)


@dataclass
class Tables:
    shots: pd.DataFrame
    player_games: pd.DataFrame
    possessions: pd.DataFrame
    rebounds: pd.DataFrame
    fouls: pd.DataFrame
    trips: pd.DataFrame
    people: pd.DataFrame
    events: pd.DataFrame | None = None
    stints: pd.DataFrame | None = None

    def window(self, season: str, games: set | None = None) -> "Tables":
        def cut(df: pd.DataFrame) -> pd.DataFrame:
            x = df[df.season == season]
            return x if games is None else x[x.gamecode.isin(games)]

        return Tables(cut(self.shots), cut(self.player_games), cut(self.possessions), cut(self.rebounds),
                      cut(self.fouls), cut(self.trips), self.people[self.people.season == season],
                      None if self.events is None else cut(self.events), None if self.stints is None else cut(self.stints))


def load_tables() -> Tables:
    read = lambda n: pd.read_parquet(TABLES_DIR / f"{n}.parquet")  # noqa: E731
    return Tables(read("shots"), read("player_games"), read("possessions"), read("rebound_chances"), read("fouls"),
                  read("ft_trips"), read("people"), read("events"), read("stints"))


def _on_court(rows: pd.DataFrame, lineup: str) -> pd.Series:
    """How many rows each player was on court for."""
    return rows[lineup].explode().value_counts().astype(float)


def counts(t: Tables, team_rebounds_count: bool = False) -> dict[str, tuple[pd.Series, pd.Series]]:
    """metric -> (successes, trials) per player, with the cleaning flags applied."""
    s, pg, po, rb = t.shots, t.player_games, t.possessions, t.rebounds
    box = pg.groupby("player_id")[["ftm", "fta", "ast", "tov", "orb", "drb", "stl", "blk", "fg2a", "fg3a"]].sum().astype(float)
    good = po[po.lineup_ok]
    off_poss, def_poss = _on_court(good, "off_lineup"), _on_court(good, "def_lineup")
    both_poss = off_poss.add(def_poss, fill_value=0)
    fga = box.fg2a + box.fg3a
    out: dict[str, tuple[pd.Series, pd.Series]] = {}

    out["ft_pct"] = (box.ftm, box.fta)
    out["stl_rate"] = (box.stl, def_poss)

    # blocks: on two-point attempts, out of the opponent's two-point attempts on court
    blocks_on_threes = s[s.blocked & (s.value == 3) & (s.blocker_id != "")].groupby("blocker_id").size().astype(float)
    blocks_on_twos = (box.blk - blocks_on_threes.reindex(box.index).fillna(0)).clip(lower=0)
    out["blk_share"] = (blocks_on_twos, _on_court(s[(s.value == 2) & s.lineup_ok], "def_lineup"))

    fouls = t.fouls[t.fouls.foul_kind.isin(FOUL_WEIGHTS)]
    foul_points = fouls.foul_kind.map(FOUL_WEIGHTS).groupby(fouls.player_id).sum()
    out["foul_rate"] = (foul_points, both_poss)

    usable = rb[rb.lineup_ok & ~rb.likely_dead]
    if not team_rebounds_count:
        usable = usable[~usable.team_rebound]
    out["orb_share"] = (box.orb, _on_court(usable, "off_lineup"))
    out["drb_share"] = (box.drb, _on_court(usable, "def_lineup"))

    touches = fga + FT_WEIGHT * box.fta + box.tov + box.ast
    out["tov_share"] = (box.tov, touches)
    out["usage_rate"] = (touches, off_poss)

    drawn = t.fouls[t.fouls.foul_kind.isin(DRAWN_KINDS) & (t.fouls.drawn_by != "")]
    out["fd_rate"] = (drawn.groupby("drawn_by").size().astype(float), off_poss)
    trips = t.trips[~t.trips.kind.isin(TRIP_EXCLUDED)]
    out["trip_rate"] = (trips.groupby("player_id").size().astype(float), off_poss)

    self_made = s[s.made & ~s.assisted & ~s.is_heave & (s.context != "putback")]
    out["creation_rate"] = (self_made.value.groupby(self_made.player_id).sum().astype(float), off_poss)

    linked = s[s.assisted].groupby("assist_player_id")
    linked_n = linked.size().astype(float)
    linked_pts = linked.value.sum().astype(float)
    ft_assists = (box.ast - linked_n.reindex(box.index).fillna(0)).clip(lower=0)
    makes = s[s.made & s.lineup_ok]
    teammate_makes = (_on_court(makes, "off_lineup")
                      .sub(makes.groupby("player_id").size().astype(float), fill_value=0).clip(lower=0))
    out["ast_share"] = (box.ast, teammate_makes.add(ft_assists, fill_value=0))
    out["created_rate"] = (linked_pts.reindex(box.index).fillna(0) + ft_assists, off_poss)

    # the shot's value comes from the scoring, so a bad coordinate does not make it any less a three
    threes = s[(s.value == 3) & ~s.is_heave]
    out["three_pct"] = (threes.groupby("player_id").made.sum().astype(float), threes.groupby("player_id").size().astype(float))
    out["three_rate"] = (out["three_pct"][1], off_poss)
    mids = s[s.zone_group == "mid"]
    out["mid_pct"] = (mids.groupby("player_id").made.sum().astype(float), mids.groupby("player_id").size().astype(float))
    out["mid_rate"] = (out["mid_pct"][1], off_poss)
    corners = s[s.zone_group == "corner3"]
    out["corner3_pct"] = (corners.groupby("player_id").made.sum().astype(float), corners.groupby("player_id").size().astype(float))

    allowed = threes[threes.lineup_ok]
    out["opp_three_pct"] = (_on_court(allowed[allowed.made], "def_lineup"), _on_court(allowed, "def_lineup"))

    # inside shots: credit relative to a league shot of the same context, on the league's scale
    inside = s[s.zone_group == "inside"]
    made = inside.made.astype(float)
    adjusted = made - made.groupby(inside.context).transform("mean") + made.mean()
    inside_attempts = inside.groupby("player_id").size().astype(float)
    out["inside_adj"] = (adjusted.groupby(inside.player_id).sum(), inside_attempts)
    out["inside_rate"] = (inside_attempts, off_poss)
    self_made = inside[inside.made & ~inside.assisted & (inside.context != "putback")]
    out["inside_self_rate"] = (self_made.groupby("player_id").size().astype(float), off_poss)
    return out


def league_level(s: pd.Series, n: pd.Series) -> float:
    """Trial-weighted league rate, counting only players with trials."""
    has = n[n > 0].index
    return float(s.reindex(has).fillna(0).sum() / n.reindex(has).sum())


def _role_features(index: pd.Index, people: pd.DataFrame, ft: pd.Series | None = None) -> pd.DataFrame:
    d = people.set_index("player_id").reindex(index)[["height", "position"]]
    d["known"] = d.height.notna() & d.position.notna()
    d["height"] = d.height.astype(float) - HEIGHT_CENTER
    d["center"] = (d.position == "Center").astype(float)
    d["forward"] = (d.position == "Forward").astype(float)
    d["ft"] = ft.reindex(index).fillna(0.0).astype(float) if ft is not None else 0.0
    return d


def fit_role(samples: list[tuple]) -> np.ndarray:
    """Weighted regression of (player rate - league level) on height, position and optionally FT skill.

    Each sample is (successes, trials, league level, people) or the same plus FT skill.
    """
    xs, ys = [], []
    for s, n, level, people, *rest in samples:
        ft = rest[0] if rest else None
        has = n[n > 0].index
        f = _role_features(has, people, ft)
        f = f[f.known]
        w = np.sqrt(n.reindex(f.index).to_numpy(float))
        columns = [np.ones(len(f)), f.height, f.center, f.forward]
        if ft is not None:
            columns.append(f.ft)
        x = np.column_stack(columns)
        y = s.reindex(f.index).fillna(0).to_numpy(float) / n.reindex(f.index).to_numpy(float) - level
        xs.append(x * w[:, None])
        ys.append(y * w)
    return np.linalg.lstsq(np.vstack(xs), np.concatenate(ys), rcond=None)[0]


def role_offset(index: pd.Index, trials: pd.Series, people: pd.DataFrame, beta: np.ndarray,
                ft: pd.Series | None = None) -> pd.Series:
    """Each player's expected gap to the league level; the window's trial-weighted mean gap is zero."""
    f = _role_features(index, people, ft)
    raw = beta[0] + beta[1] * f.height + beta[2] * f.center + beta[3] * f.forward
    if len(beta) > 4:
        raw = raw + beta[4] * f.ft
    raw = pd.Series(raw, index=index).where(f.known)
    w = trials.reindex(index).fillna(0)
    known = raw.notna()
    mean = (raw[known] * w[known]).sum() / max(w[known].sum(), 1.0)
    return (raw - mean).fillna(0.0)


def ft_skill(made: pd.Series, attempts: pd.Series, past: list[tuple] | None = None) -> pd.Series:
    """Free-throw skill relative to the league, for use inside other metrics' priors."""
    level = league_level(made, attempts)
    theta, _, _ = shrink(made, attempts, Spec("prop", FT_SKILL_PRIOR), level, past=past)
    return theta - level


def shrink(s: pd.Series, n: pd.Series, spec: Spec, level: float, offset: pd.Series | None = None,
           past: list[tuple[pd.Series, pd.Series, float, float]] | None = None, index: pd.Index | None = None
           ) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Shrunk estimate, total trials and standard error, all in raw (not display) units.

    past holds (successes, trials, that season's league level, weight). Past counts are moved to
    this season's league level, so a league-wide change does not read as a change in the player.
    """
    idx = s.index.union(n.index) if index is None else index
    total_s, total_n = s.reindex(idx).fillna(0).astype(float), n.reindex(idx).fillna(0).astype(float)
    if spec.kind == "resid":  # signed: no bounds on the prior, and a variance that does not depend on the level
        prior = level + (offset.reindex(idx).fillna(0) if offset is not None else 0.0)
        for ps, pn, past_level, weight in past or []:
            pn_ = pn.reindex(idx).fillna(0).astype(float)
            total_s = total_s + weight * (ps.reindex(idx).fillna(0) + (level - past_level) * pn_)
            total_n = total_n + weight * pn_
        theta = (total_s + spec.k * prior) / (total_n + spec.k)
        return theta, total_n, pd.Series(np.sqrt(spec.dispersion / (total_n + spec.k)), index=idx)
    for ps, pn, past_level, weight in past or []:
        pn_ = pn.reindex(idx).fillna(0).astype(float)
        total_s = total_s + weight * (ps.reindex(idx).fillna(0) + (level - past_level) * pn_)
        total_n = total_n + weight * pn_
    prior = level + (offset.reindex(idx).fillna(0) if offset is not None else 0.0)
    if spec.kind == "prop":
        prior = pd.Series(prior, index=idx).clip(0.001, 0.999)
    else:
        prior = pd.Series(prior, index=idx).clip(lower=level * 0.05)
    theta = (total_s.clip(lower=0) + spec.k * prior) / (total_n + spec.k)
    variance = theta * (1 - theta) if spec.kind == "prop" else theta
    return theta, total_n, np.sqrt(spec.dispersion * variance.clip(lower=0) / (total_n + spec.k))


@dataclass
class _Context:
    seasons: list[str]
    windows: dict[str, Tables]
    counts: dict[str, dict]
    levels: dict[str, dict[str, float]]
    base: dict[str, float]
    betas: dict[str, np.ndarray]
    ft: dict[str, pd.Series]

    def history(self, i: int, metric: str, carry: float) -> list[tuple]:
        out = []
        for back, weight in ((1, carry), (2, carry * TWO_BACK_FACTOR)):
            if carry > 0 and i >= back:
                prev = self.seasons[i - back]
                out.append((*self.counts[prev][metric], self.levels[prev][metric], weight))
        return out


def _context(t: Tables, specs: dict[str, Spec], reference_seasons) -> _Context:
    seasons = sorted(t.player_games.season.unique())
    windows = {x: t.window(x) for x in seasons}
    all_counts = {x: counts(w) for x, w in windows.items()}
    levels = {x: {m: league_level(*c[m]) for m in specs} for x, c in all_counts.items()}
    base = {m: float(np.mean([levels[x][m] for x in reference_seasons if x in levels])) for m in specs}
    ctx = _Context(seasons, windows, all_counts, levels, base, {}, {})
    ctx.ft = {x: ft_skill(*all_counts[x]["ft_pct"], ctx.history(i, "ft_pct", 1.0)) for i, x in enumerate(seasons)}
    for m, sp in specs.items():
        if sp.role:
            ctx.betas[m] = fit_role([(*all_counts[x][m], levels[x][m], windows[x].people, *([ctx.ft[x]] if sp.ft_prior else []))
                                     for x in reference_seasons if x in windows])
    return ctx


def _meta(pg: pd.DataFrame) -> pd.DataFrame:
    meta = pg.groupby("player_id").agg(player=("player", "last"), team=("team", "last"), games=("gamecode", "size"),
                                       minutes=("minutes", "sum"))
    return meta.assign(mpg=meta.minutes / meta.games)


def season_metrics(t: Tables, specs: dict[str, Spec] = SPECS, reference_seasons=REFERENCE_SEASONS) -> pd.DataFrame:
    """One row per player-season: estimates, trials, standard errors, compared to the league at that time."""
    ctx = _context(t, specs, reference_seasons)
    frames = []
    for i, season in enumerate(ctx.seasons):
        w = ctx.windows[season]
        m = _meta(w.player_games).assign(season=season)
        relative: dict[str, pd.Series] = {}
        for metric, spec in specs.items():
            s, n = ctx.counts[season][metric]
            level = ctx.levels[season][metric]
            if spec.prior_from:
                offset = relative[spec.prior_from]
            elif spec.role:
                offset = role_offset(m.index, n, w.people, ctx.betas[metric], ctx.ft[season] if spec.ft_prior else None)
            else:
                offset = None
            theta, total, se = shrink(s, n, spec, level, offset, ctx.history(i, metric, spec.carry), m.index)
            relative[metric] = theta - level
            m[metric] = spec.scale * (theta - level + ctx.base[metric])
            m[f"n_{metric}"] = total
            m[f"se_{metric}"] = spec.scale * se
            if metric in RELATIVE_METRICS:
                m[f"rel_{metric}"] = relative[metric]
        s, n = ctx.counts[season]["three_rate"]
        raw_rate = 100 * s.reindex(m.index).fillna(0) / n.reindex(m.index).clip(lower=1).fillna(1)
        m["three_non_shooter"] = (m["n_three_pct"] < NON_SHOOTER_ATTEMPTS) & (raw_rate < NON_SHOOTER_RATE)
        mid_attempts = ctx.counts[season]["mid_rate"][0].reindex(m.index).fillna(0)
        m["mid_non_shooter"] = (m["n_mid_pct"] < NON_SHOOTER_ATTEMPTS) & (mid_attempts / m.games <= MID_NON_SHOOTER_PER_GAME)
        past_attempts = ctx.counts[ctx.seasons[i - 1]]["three_rate"][0] if i else pd.Series(dtype=float)
        past_games = ctx.windows[ctx.seasons[i - 1]].player_games.groupby("player_id").gamecode.nunique() if i else pd.Series(dtype=float)
        frames.append(add_three_value(m, s, past_attempts / past_games).reset_index())
    return pd.concat(frames, ignore_index=True)


def add_three_value(m: pd.DataFrame, attempts: pd.Series, usual_per_game: pd.Series) -> pd.DataFrame:
    """Points per game above a base shooter on his attempts: 3 x attempts x (make rate - base).

    Attempts and accuracy multiply, so neither carries a rating alone: a few accurate attempts add
    little, and many attempts add little at a middling rate. Attempts stay close to what he really
    shoots: a volume estimate that drifts toward his role would lift exactly the low-volume players
    this rating should hold back. The small pull only stops one hot game from moving it.
    """
    made_up = THREE_ATTEMPT_PRIOR_GAMES
    usual = usual_per_game.reindex(m.index)
    usual = usual.fillna(float(usual.mean()) if usual.notna().any() else 0.0)
    total = attempts.reindex(m.index).fillna(0.0).astype(float)
    per_game = (total + made_up * usual) / (m.games + made_up)
    above = m.three_pct - THREE_BASE_PCT
    se_attempts = np.sqrt(per_game.clip(lower=0) / (m.games + made_up))
    m["three_attempts_game"] = per_game
    m["three_value"] = 3 * per_game * above
    m["n_three_value"] = m.n_three_pct
    m["se_three_value"] = 3 * np.sqrt((per_game * m.se_three_pct) ** 2 + (above * se_attempts) ** 2)
    return m


def months_of(pg: pd.DataFrame) -> pd.Series:
    """Calendar month of each game code in one season's table."""
    return pg.groupby("gamecode").date.first().dt.tz_convert(None).dt.to_period("M")


def month_metrics(t: Tables, specs: dict[str, Spec] = SPECS, reference_seasons=REFERENCE_SEASONS) -> pd.DataFrame:
    """A month's estimates, pulled toward the player's level before that month.

    This answers "was he in form?": a month away from his own level moves the number, a month
    in line with it does not. The level comes from earlier games this season, past seasons and role.
    """
    ctx = _context(t, specs, reference_seasons)
    empty = pd.Series(dtype=float)
    frames = []
    for i, season in enumerate(ctx.seasons):
        w = ctx.windows[season]
        month_map = months_of(w.player_games)
        before: set = set()
        for month in sorted(month_map.unique()):
            games = set(month_map.index[month_map == month])
            now = t.window(season, games)
            current = counts(now)
            earlier = counts(t.window(season, before)) if before else None
            m = _meta(now.player_games).assign(season=season, month=str(month))
            history_ft = ctx.history(i, "ft_pct", 1.0)
            ft = (ft_skill(*earlier["ft_pct"], history_ft) if earlier else
                  (ft_skill(empty, empty, history_ft) if history_ft else None))
            for metric, spec in specs.items():
                if metric in INFO_METRICS:
                    continue
                level = ctx.levels[season][metric]
                s0, n0 = earlier[metric] if earlier else (empty, empty)
                offset = None
                if spec.role:
                    offset = role_offset(m.index, ctx.counts[season][metric][1], w.people, ctx.betas[metric], ft if spec.ft_prior else None)
                pre, _, _ = shrink(s0, n0, spec, level, offset, ctx.history(i, metric, spec.carry), m.index)
                s, n = current[metric]
                month_level = league_level(s, n) if n[n > 0].sum() > 0 else level
                plain = Spec(spec.kind, spec.k, dispersion=spec.dispersion)
                theta, total, se = shrink(s, n, plain, month_level, pre - level, None, m.index)
                m[metric] = spec.scale * (theta - month_level + ctx.base[metric])
                m[f"n_{metric}"] = total
                m[f"se_{metric}"] = spec.scale * se
            earlier_attempts = earlier["three_rate"][0] if earlier else pd.Series(dtype=float)
            earlier_games = t.window(season, before).player_games.groupby("player_id").gamecode.nunique() if earlier else pd.Series(dtype=float)
            frames.append(add_three_value(m, current["three_rate"][0], earlier_attempts / earlier_games).reset_index())
            before |= games
    return pd.concat(frames, ignore_index=True)


def tier_label(rating: int) -> str:
    return "Düşük" if rating <= TIER_LOW_MAX else "Orta" if rating <= TIER_MEDIUM_MAX else "Yüksek"


def display_value(attribute: str, rating: int, non_shooter: bool = False, games: int | None = None,
                  mid_non_shooter: bool = False) -> str:
    """What the card shows: a number, a tier, or a plain statement when there is nothing to rate."""
    if attribute == "consistency" and games is not None and games < CONSISTENCY_MIN_GAMES:
        return "Az veri"
    if attribute == "three_point" and non_shooter:
        return "Üçlük kullanmıyor"
    if attribute == "mid_range" and mid_non_shooter:
        return "Orta mesafe kullanmıyor"
    if attribute in TIER_ATTRIBUTES:
        return tier_label(rating)
    return str(rating)


def score_frames(metrics: pd.DataFrame, attributes=ATTRIBUTES_V2, specs: dict[str, Spec] = SPECS) -> pd.DataFrame:
    """Score every player-season against the fixed reference."""
    from bk.ratings.method import score_fixed

    reference = fixed_reference(metrics)
    prior_k = {m: sp.k for m, sp in specs.items() if m not in INFO_METRICS}
    if "three_pct" in specs:
        prior_k["three_value"] = specs["three_pct"].k
    frames = [score_fixed(g.set_index("player_id"), reference, attributes, prior_k).assign(season=season).reset_index()
              for season, g in metrics.groupby("season")]
    return pd.concat(frames, ignore_index=True)
