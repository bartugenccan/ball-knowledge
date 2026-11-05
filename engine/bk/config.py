import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# the deployed API carries only the tables it serves, so it says where they are
DATA_DIR = Path(os.environ["BK_DATA_DIR"]) if os.environ.get("BK_DATA_DIR") else REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
TABLES_DIR = DATA_DIR / "tables"
AUDIT_DIR = DATA_DIR / "audit"

COMPETITION = "E"  # EuroLeague; "U" would be EuroCup
