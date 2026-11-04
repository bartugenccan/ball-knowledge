"""Lineup models that separate a player's defensive effect from his teammates'.

For each defensive lineup we know what opponents produced per possession. A ridge regression
then splits that among the players on court, pulling each estimate toward a prior: zero, the
player's role, or last season's estimate. lam works like k elsewhere: the number of possessions
of evidence the prior is worth. No tracking data exists, so these remain estimates of on-court
effect, not measurements of who guarded whom.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from bk.ratings.attributes import Attribute
from bk.ratings.method import REFERENCE_SEASONS
from bk.ratings.metrics_v2 import HEIGHT_CENTER, Spec, Tables, counts, league_level, months_of, shrink

GAME = ["season", "gamecode", "poss_no"]
TARGETS = ("inside_points", "inside_fga", "three_attempts", "points")
BLOCK_PRIOR = Spec("prop", 40)
REBOUND_PRIOR = Spec("prop", 200)


def possession_table(t: Tables) -> pd.DataFrame:
    """One row per clean possession: lineups as text keys and what the opponent produced."""
    po = t.possessions[t.possessions.lineup_ok]
    d = po[GAME + ["points"] + (["defense"] if "defense" in po else [])].copy()
    d["def_key"] = po.def_lineup.map("|".join)
    d["off_key"] = po.off_lineup.map("|".join)
    s = t.shots
    inside = s[s.zone_group == "inside"]
    threes = s[(s.value == 3) & ~s.is_heave]
    produced = pd.DataFrame({
        "inside_points": (2 * inside.made.astype(float)).groupby([inside[c] for c in GAME]).sum(),
        "inside_fga": inside.groupby(GAME).size().astype(float),
        "three_attempts": threes.groupby(GAME).size().astype(float),
    })
    d = d.join(produced, on=GAME)
    d[list(produced.columns)] = d[list(produced.columns)].fillna(0.0)
    d["points"] = d.points.astype(float)
    return d


TEAM_PENALTY = 1.0  # team effects are almost free: only players are pulled toward a prior


def _rows(poss: pd.DataFrame, target: str, use_offense: bool, use_team: bool = False) -> pd.DataFrame:
    keys = (["def_key", "off_key"] if use_offense else ["def_key"]) + (["defense"] if use_team else [])
    return poss.groupby(keys, sort=False)[target].agg(total="sum", n="size").reset_index()


@dataclass
class Design:
    """Normal equations for one window, ready to solve for any lam and prior."""

    players: list[str]             # "D:<id>" for defenders, "O:<id>" for offensive players
    gram: np.ndarray
    rhs: np.ndarray
    mean: float
    variance: float
    possessions: pd.Series         # defensive possessions per player

    def _system(self, lam: float) -> np.ndarray:
        penalty = np.array([TEAM_PENALTY if name.startswith("T:") else lam for name in self.players])
        return self.gram + np.diag(penalty)

    @classmethod
    def build(cls, poss: pd.DataFrame, target: str, use_offense: bool = False, use_team: bool = False) -> "Design":
        """use_team adds a free effect per defending team, so players are compared within their team."""
        rows = _rows(poss, target, use_offense, use_team)
        mean = float(poss[target].mean())
        def_lists = rows.def_key.str.split("|")
        off_lists = rows.off_key.str.split("|") if use_offense else None
        names = sorted({f"D:{p}" for lineup in def_lists for p in lineup}
                       | ({f"O:{p}" for lineup in off_lists for p in lineup} if use_offense else set())
                       | ({f"T:{x}" for x in rows.defense} if use_team else set()))
        index = {name: i for i, name in enumerate(names)}
        gram = np.zeros((len(names), len(names)))
        rhs = np.zeros(len(names))
        possessions: dict[str, float] = {}
        for i, (total, n) in enumerate(zip(rows.total.to_numpy(float), rows.n.to_numpy(float))):
            idx = [index[f"D:{p}"] for p in def_lists.iloc[i]]
            for p in def_lists.iloc[i]:
                possessions[p] = possessions.get(p, 0.0) + n
            if use_offense:
                idx += [index[f"O:{p}"] for p in off_lists.iloc[i]]
            if use_team:
                idx.append(index[f"T:{rows.defense.iloc[i]}"])
            gram[np.ix_(idx, idx)] += n
            rhs[idx] += total - mean * n
        return cls(names, gram, rhs, mean, float(poss[target].var()), pd.Series(possessions))

    def solve(self, lam: float, prior: pd.Series | None = None) -> pd.DataFrame:
        """Effect per possession (positive = opponent produces more), standard error, possessions."""
        mu = np.zeros(len(self.players))
        if prior is not None:
            for i, name in enumerate(self.players):
                if name.startswith("D:"):
                    mu[i] = prior.get(name[2:], 0.0)
        system = self._system(lam)
        beta = np.linalg.solve(system, self.rhs + lam * mu)
        inverse_diagonal = np.diag(np.linalg.inv(system))
        out = pd.DataFrame({"beta": beta, "se": np.sqrt(self.variance * inverse_diagonal)}, index=self.players)
        out = out[out.index.str.startswith("D:")]
        out.index = out.index.str[2:]
        out.index.name = "player_id"
        out["n"] = self.possessions.reindex(out.index).fillna(0.0)
        return out


def holdout_gain(train: pd.DataFrame, test: pd.DataFrame, target: str, lam: float, prior: pd.Series | None = None,
                 use_offense: bool = False, design: Design | None = None) -> float:
    """% less squared error than a constant when predicting another window's lineups."""
    d = design or Design.build(train, target, use_offense)
    system = d.gram + lam * np.eye(len(d.players))
    mu = np.zeros(len(d.players))
    if prior is not None:
        for i, name in enumerate(d.players):
            if name.startswith("D:"):
                mu[i] = prior.get(name[2:], 0.0)
    beta = dict(zip(d.players, np.linalg.solve(system, d.rhs + lam * mu)))
    rows = _rows(test, target, use_offense)
    level = float(test[target].mean())
    pred = rows.def_key.map(lambda k: sum(beta.get(f"D:{p}", 0.0) for p in k.split("|")))
    if use_offense:
        pred = pred + rows.off_key.map(lambda k: sum(beta.get(f"O:{p}", 0.0) for p in k.split("|")))
    y = rows.total / rows.n
    weights = rows.n
    baseline = float((weights * (y - level) ** 2).sum())
    return 100 * (1 - float((weights * (y - level - pred) ** 2).sum()) / baseline)


def role_features(t: Tables, counts_: dict, index: pd.Index) -> pd.DataFrame:
    """Height, position, and shrunk block and defensive rebound shares relative to the league."""
    people = t.people.set_index("player_id").reindex(index)
    f = pd.DataFrame(index=index)
    f["height"] = people.height.astype(float) - HEIGHT_CENTER
    f["center"] = (people.position == "Center").astype(float)
    f["forward"] = (people.position == "Forward").astype(float)
    f["known"] = people.height.notna() & people.position.notna()
    for name, metric, spec in (("blk", "blk_share", BLOCK_PRIOR), ("drb", "drb_share", REBOUND_PRIOR)):
        s, n = counts_[metric]
        level = league_level(s, n)
        theta, _, _ = shrink(s, n, spec, level, index=index)
        f[name] = theta - level
    return f


FEATURES = ["height", "center", "forward", "blk", "drb"]


def fit_role_effect(effects: list[pd.Series], features: list[pd.DataFrame], weights: list[pd.Series]) -> np.ndarray:
    """Regress lineup-model effects on role features, weighted by possessions."""
    xs, ys = [], []
    for beta, f, w in zip(effects, features, weights):
        common = beta.index.intersection(f.index[f.known])
        root = np.sqrt(w.reindex(common).fillna(0).to_numpy(float))
        x = np.column_stack([np.ones(len(common))] + [f.loc[common, c].to_numpy(float) for c in FEATURES])
        xs.append(x * root[:, None])
        ys.append(beta.reindex(common).to_numpy(float) * root)
    return np.linalg.lstsq(np.vstack(xs), np.concatenate(ys), rcond=None)[0]


def role_prior(f: pd.DataFrame, coefficients: np.ndarray, weights: pd.Series) -> pd.Series:
    """Expected effect from the player's role; the window's possession-weighted mean is zero."""
    known = f[f.known]
    raw = pd.Series(coefficients[0] + sum(c * known[name] for c, name in zip(coefficients[1:], FEATURES)), index=known.index)
    w = weights.reindex(raw.index).fillna(0)
    return raw - (raw * w).sum() / max(w.sum(), 1.0)


def on_off_card(t: Tables, poss: pd.DataFrame | None = None) -> pd.DataFrame:
    """On-court and off-court opponent inside numbers per player-season, in the games he played."""
    d = possession_table(t) if poss is None else poss
    po = t.possessions[t.possessions.lineup_ok][GAME + ["defense"]]
    d = d.drop(columns="defense", errors="ignore").merge(po, on=GAME)
    d["inside_makes"] = d.inside_points / 2
    keys = ["season", "gamecode", "defense"]
    totals = d.groupby(keys)[["inside_fga", "inside_makes"]].sum().assign(n=d.groupby(keys).size())
    on = d.assign(player_id=d.def_key.str.split("|")).explode("player_id")
    per = on.groupby(["player_id"] + keys)[["inside_fga", "inside_makes"]].sum().assign(n=on.groupby(["player_id"] + keys).size())
    per = per.join(totals.add_suffix("_team"), on=keys).reset_index()
    per["n_off"] = per.n_team - per.n
    per["fga_off"] = per.inside_fga_team - per.inside_fga
    per["makes_off"] = per.inside_makes_team - per.inside_makes
    a = per.groupby(["season", "player_id"])[["n", "inside_fga", "inside_makes", "n_off", "fga_off", "makes_off"]].sum()
    return pd.DataFrame({
        "opp_inside_fga_on": 100 * a.inside_fga / a.n.clip(lower=1), "opp_inside_fga_off": 100 * a.fga_off / a.n_off.clip(lower=1),
        "opp_inside_pct_on": a.inside_makes / a.inside_fga.clip(lower=1), "opp_inside_pct_off": a.makes_off / a.fga_off.clip(lower=1),
    }).reset_index()


PREV_WEIGHT = 0.5


@dataclass(frozen=True)
class EffectConfig:
    target: str
    lam: float
    prior: str = "yok"        # "yok", "rol", "geçmiş" (last season x PREV_WEIGHT) or "ikisi" (their mean)
    use_team: bool = False    # compare players within their team
    use_offense: bool = False


# Choices and their test results: scripts/audit/stage5.py
EFFECTS = {
    "rim_effect": EffectConfig("inside_points", 1500, "ikisi", use_team=True),
    "three_att_effect": EffectConfig("three_attempts", 3000, "geçmiş", use_team=True),
    "team_effect": EffectConfig("points", 6000, "geçmiş"),
}
RIM_BLOCK_WEIGHT = 0.5

DEFENSE_ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute("rim_protection", "Pota Koruma", "savunma", "tahmini",
              (("rim_effect", 1 - RIM_BLOCK_WEIGHT, 1), ("blk_share", RIM_BLOCK_WEIGHT, 1)),
              "Sahadayken rakibin boyalı alan sayısına etkisi (takım arkadaşları ve takımdan ayrılmış) ve blok payı"),
    Attribute("perimeter_defense", "Çevre Savunması", "savunma", "tahmini",
              (("three_att_effect", .5, 1), ("stl_rate", .3, 1), ("opp_three_pct", .2, -1)),
              "Sahadayken rakibin üçlük denemesine etkisi, top çalma payı ve rakibin üçlük isabeti"),
    Attribute("team_defense", "Savunma Etkisi", "savunma", "tahmini", (("team_effect", 1, 1),),
              "Sahadayken rakibin sayısına etkisi, takım arkadaşlarından ayrılmış"),
)
DEFENSE_K = {name: cfg.lam for name, cfg in EFFECTS.items()}


def _season_priors(t: Tables, poss: dict[str, pd.DataFrame], cfg: EffectConfig, seasons: list[str],
                   role_fit_seasons=REFERENCE_SEASONS) -> tuple[dict[str, "Design"], dict[str, pd.Series | None]]:
    designs, plain, features = {}, {}, {}
    for x in seasons:
        designs[x] = Design.build(poss[x], cfg.target, cfg.use_offense, cfg.use_team)
        plain[x] = designs[x].solve(cfg.lam)
    if cfg.prior in ("rol", "ikisi"):
        for x in seasons:
            features[x] = role_features(t.window(x), counts(t.window(x)), plain[x].index)
        fit = [x for x in role_fit_seasons if x in plain]
        coefficients = fit_role_effect([plain[x].beta for x in fit], [features[x] for x in fit], [plain[x].n for x in fit])
    priors: dict[str, pd.Series | None] = {}
    for i, x in enumerate(seasons):
        previous = PREV_WEIGHT * plain[seasons[i - 1]].beta if i > 0 else None
        role = role_prior(features[x], coefficients, plain[x].n) if cfg.prior in ("rol", "ikisi") else None
        if cfg.prior == "rol":
            priors[x] = role
        elif cfg.prior == "geçmiş":
            priors[x] = previous
        elif cfg.prior == "ikisi":
            priors[x] = role if previous is None else 0.5 * previous.reindex(role.index).fillna(0) + 0.5 * role
        else:
            priors[x] = None
    return designs, priors


def _frame(fitted: pd.DataFrame, **columns) -> pd.DataFrame:
    return pd.DataFrame({**columns, "player_id": fitted.index, "effect": -100 * fitted.beta.to_numpy(),
                         "se": 100 * fitted.se.to_numpy(), "n": fitted.n.to_numpy()})


def build_effect(t: Tables, poss: dict[str, pd.DataFrame], cfg: EffectConfig, seasons: list[str],
                 role_fit_seasons=REFERENCE_SEASONS) -> pd.DataFrame:
    """Effect per 100 possessions for every season; positive means a better defense."""
    designs, priors = _season_priors(t, poss, cfg, seasons, role_fit_seasons)
    return pd.concat([_frame(designs[x].solve(cfg.lam, priors[x]), season=x) for x in seasons], ignore_index=True)


def month_effects(t: Tables, poss: dict[str, pd.DataFrame], cfg: EffectConfig, seasons: list[str]) -> pd.DataFrame:
    """A month's effect, pulled toward the player's estimate from before that month."""
    _, priors = _season_priors(t, poss, cfg, seasons)
    frames = []
    for x in seasons:
        month_map = months_of(t.window(x).player_games)
        before: set = set()
        prior = priors[x]
        for month in sorted(month_map.unique()):
            games = set(month_map.index[month_map == month])
            if before:
                earlier = poss[x][poss[x].gamecode.isin(before)]
                prior = Design.build(earlier, cfg.target, cfg.use_offense, cfg.use_team).solve(cfg.lam, priors[x]).beta
            now = poss[x][poss[x].gamecode.isin(games)]
            fitted = Design.build(now, cfg.target, cfg.use_offense, cfg.use_team).solve(cfg.lam, prior)
            frames.append(_frame(fitted, season=x, month=str(month)))
            before |= games
    return pd.concat(frames, ignore_index=True)


def attach_effect(metrics: pd.DataFrame, effect: pd.DataFrame, name: str, keys=("season", "player_id")) -> pd.DataFrame:
    """Players without defensive possessions get a neutral effect and the widest uncertainty."""
    d = effect.rename(columns={"effect": name, "se": f"se_{name}", "n": f"n_{name}"})
    out = metrics.merge(d, on=list(keys), how="left")
    out[name] = out[name].fillna(0.0)
    out[f"se_{name}"] = out[f"se_{name}"].fillna(out[f"se_{name}"].max())
    out[f"n_{name}"] = out[f"n_{name}"].fillna(0.0)
    return out


def add_defense_metrics(t: Tables, metrics: pd.DataFrame) -> pd.DataFrame:
    seasons = sorted(metrics.season.unique())
    poss = {x: possession_table(t.window(x)) for x in seasons}
    out = metrics
    for name, cfg in EFFECTS.items():
        out = attach_effect(out, build_effect(t, poss, cfg, seasons), name)
    return out


def add_defense_months(t: Tables, metrics: pd.DataFrame) -> pd.DataFrame:
    seasons = sorted(metrics.season.unique())
    poss = {x: possession_table(t.window(x)) for x in seasons}
    out = metrics
    for name, cfg in EFFECTS.items():
        out = attach_effect(out, month_effects(t, poss, cfg, seasons), name, ("season", "month", "player_id"))
    return out
