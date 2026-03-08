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


def update_trip(user_id: int, trip_id: str, updates: dict) -> dict | None:
    trips = load_trips(user_id)
    for t in trips:
        if t["id"] == trip_id:
            t.update(updates)
            save_trips(user_id, trips)
            return t
    return None
