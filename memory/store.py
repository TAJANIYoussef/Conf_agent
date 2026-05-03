import json
import os
import logging
from datetime import date
from agent.models import Conference
from agent.config import MEMORY_FILE

logger = logging.getLogger(__name__)

def _load() -> dict:
    if not os.path.exists(MEMORY_FILE):
        return {"seen_acronyms": [], "calendar_ids": {}, "runs": []}
    with open(MEMORY_FILE) as f:
        return json.load(f)

def _save(data: dict):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)

def get_seen_acronyms() -> set[str]:
    return set(_load().get("seen_acronyms", []))

def mark_added(conf: Conference, calendar_event_id: str):
    data = _load()
    key = f"{conf.acronym.upper()}{conf.year}"
    if key not in data["seen_acronyms"]:
        data["seen_acronyms"].append(key)
    data["calendar_ids"][key] = calendar_event_id
    _save(data)

def record_run(conferences_added: int, cost_usd: float):
    data = _load()
    data.setdefault("runs", []).append({
        "date":               date.today().isoformat(),
        "conferences_added":  conferences_added,
        "cost_usd":           cost_usd,
    })
    _save(data)

def get_run_history() -> list[dict]:
    return _load().get("runs", [])
