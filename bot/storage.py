"""Simple JSON file storage per user, matching Trippa data format."""

import json
import os
import time
import random
import string

from config import DATA_DIR


def _user_file(user_id: int) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, f"{user_id}.json")


def all_user_ids() -> list[int]:
    """Return list of all user IDs that have data files."""
    os.makedirs(DATA_DIR, exist_ok=True)
    ids = []
    for name in os.listdir(DATA_DIR):
        if name.endswith(".json"):
            try:
                ids.append(int(name[:-5]))
            except ValueError:
                pass
    return ids


def load_trips(user_id: int) -> list[dict]:
    path = _user_file(user_id)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_trips(user_id: int, trips: list[dict]) -> None:
    path = _user_file(user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trips, f, ensure_ascii=False, indent=2)


def gen_id() -> str:
    ts = int(time.time() * 1000)
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{ts:x}{rand}"


def add_trip(user_id: int, name: str, trip_type: str, cities: list[dict], notif_days: int = 1) -> dict:
    trips = load_trips(user_id)
    trip = {
        "id": gen_id(),
        "name": name,
        "type": trip_type,
        "cities": cities,
        "notifDays": notif_days,
    }
    trips.append(trip)
    save_trips(user_id, trips)
    return trip


def delete_trip(user_id: int, trip_id: str) -> bool:
    trips = load_trips(user_id)
    new_trips = [t for t in trips if t["id"] != trip_id]
    if len(new_trips) == len(trips):
        return False
    save_trips(user_id, new_trips)
    return True


# ── Voice usage tracking ──────────────────────────────────────────────

_VOICE_FILE = os.path.join(DATA_DIR, "_voice_usage.json")


def _load_voice_data() -> dict:
    if os.path.exists(_VOICE_FILE):
        with open(_VOICE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_voice_data(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_VOICE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_voice_count(user_id: int) -> int:
    data = _load_voice_data()
    entry = data.get(str(user_id), {})
    return entry.get("count", 0)


def increment_voice_count(user_id: int) -> int:
    data = _load_voice_data()
    key = str(user_id)
    if key not in data:
        data[key] = {"count": 0, "premium": False}
    data[key]["count"] = data[key].get("count", 0) + 1
    _save_voice_data(data)
    return data[key]["count"]


def is_premium(user_id: int) -> bool:
    data = _load_voice_data()
    entry = data.get(str(user_id), {})
    return entry.get("premium", False)


def set_premium(user_id: int, value: bool = True) -> None:
    data = _load_voice_data()
    key = str(user_id)
    if key not in data:
        data[key] = {"count": 0, "premium": False}
    data[key]["premium"] = value
    _save_voice_data(data)


def update_trip(user_id: int, trip_id: str, updates: dict) -> dict | None:
    trips = load_trips(user_id)
    for t in trips:
        if t["id"] == trip_id:
            t.update(updates)
            save_trips(user_id, trips)
            return t
    return None
