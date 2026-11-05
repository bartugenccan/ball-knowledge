"""Which team tendencies are real? Measured on E2024 and E2025.

    uv run python scripts/audit/team_style_reliability.py

A style sentence should describe a team, not a good week. Each tendency is scored by how well a team's
first ten games predict the rest of its season, and one half of its games the other half. Below 0.60
on the first test, a tendency is still shown but gets no sentence, and the page marks it as unsteady.

Writes data/audit/team_style_reliability.json, read by bk.team.style, and a table for people.
"""

from __future__ import annotations

import json
import warnings

warnings.filterwarnings("ignore")

from bk.config import AUDIT_DIR  # noqa: E402
from bk.ratings.metrics_v2 import load_tables  # noqa: E402
from bk.team.style import BY_KEY, MIN_STABILITY, RELIABILITY_FILE, stability, team_game_counts  # noqa: E402


def main() -> None:
    table = stability(team_game_counts(load_tables()))
    RELIABILITY_FILE.write_text(json.dumps(table, indent=1), encoding="utf-8")
    lines = ["# Takım eğilimlerinin güvenilirliği", "", "E2024 ve E2025 ortalaması. İlk 10 maç / kalan maçlar, tek / çift maçlar.", "",
             "| Eğilim | İlk 10 → kalan | Tek → çift | Cümle hakkı |", "|---|---:|---:|---|"]
    for key, v in sorted(table.items(), key=lambda kv: -kv[1]["first_ten_vs_rest"]):
        lines.append(f"| {BY_KEY[key].label} | {v['first_ten_vs_rest']:.2f} | {v['split_half']:.2f} | {'evet' if v['first_ten_vs_rest'] >= MIN_STABILITY else 'hayır'} |")
    out = "\n".join(lines) + "\n"
    (AUDIT_DIR / "team_style_reliability.md").write_text(out, encoding="utf-8")
    print(out.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
