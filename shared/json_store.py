
import json
from pathlib import Path
def load_json(path, default):
    p = Path(path)
    if not p.exists():
        p.write_text(json.dumps(default, indent=2), encoding="utf-8")
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default
def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
