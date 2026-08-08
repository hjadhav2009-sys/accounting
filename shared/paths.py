
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
UPLOADS_DIR = ROOT / "uploads"
LOGS_DIR = ROOT / "logs"
for p in [DATA_DIR, OUTPUT_DIR, UPLOADS_DIR, LOGS_DIR]:
    p.mkdir(exist_ok=True)
