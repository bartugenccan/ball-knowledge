"""Does each defensive effect follow the player to a new team? Read-only.

    uv run python scripts/audit/stage5_movers.py
"""
import warnings

import pandas as pd

warnings.simplefilter("ignore")
from bk.ratings.defense import EffectConfig, build_effect, possession_table
from bk.ratings.metrics_v2 import load_tables

t = load_tables()
seasons = ["E2024", "E2025"]
poss = {x: possession_table(t.window(x)) for x in seasons}
pg = t.player_games[t.player_games.season.isin(seasons)]
info = pg.groupby(["season", "player_id"]).agg(team=("team", "last"), minutes=("minutes", "sum")).reset_index()
wide = info.pivot(index="player_id", columns="season", values=["team", "minutes"])
ok = wide[(wide[("minutes", "E2024")] >= 500) & (wide[("minutes", "E2025")] >= 500)]
stay = ok[ok[("team", "E2024")] == ok[("team", "E2025")]].index
move = ok[ok[("team", "E2024")] != ok[("team", "E2025")]].index
print("stayed", len(stay), "moved", len(move))
for label, cfg in (("Savunma Etkisi (takım ayrımı yok)", EffectConfig("points", 6000)),
                   ("Çevre: üçlük denemesi etkisi", EffectConfig("three_attempts", 3000, use_team=True)),
                   ("Pota: saha içi etki", EffectConfig("inside_points", 1500, use_team=True))):
    e = build_effect(t, poss, cfg, seasons)
    p = e.pivot(index="player_id", columns="season", values="effect")
    print(f"{label}: aynı takım r={p.loc[p.index.intersection(stay)].corr().iloc[0, 1]:.3f}, takım değiştiren r={p.loc[p.index.intersection(move)].corr().iloc[0, 1]:.3f}")
