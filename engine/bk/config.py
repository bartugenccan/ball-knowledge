from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
TABLES_DIR = DATA_DIR / "tables"
AUDIT_DIR = DATA_DIR / "audit"

COMPETITION = "E"  # EuroLeague; "U" would be EuroCup
