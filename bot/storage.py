"""Simple JSON file storage per user, matching Trippa data format."""

import json
import logging
import os
import random
import string
import tempfile
import time

from config import DATA_DIR

logger = logging.getLogger(__name__)


def _user_file(user_id: int) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, f"{user_id}.json")


def load_trips(user_id: int) -> list[dict]:
    path = _user_file(user_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("Expected list at top level")
            return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Corrupted data file for user %s: %s", user_id, e)
        corrupt_path = path + ".corrupt"
        try:
            os.rename(path, corrupt_path)
        except OSError:
            pass
        return []


def save_trips(user_id: int, trips: list[dict]) -> None:
    path = _user_file(user_id)
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(trips, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


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
    logger.info("User %s created trip %s (%s)", user_id, trip["id"], name)
    return trip


def delete_trip(user_id: int, trip_id: str) -> bool:
    trips = load_trips(user_id)
    new_trips = [t for t in trips if t["id"] != trip_id]
    if len(new_trips) == len(trips):
        return False
    save_trips(user_id, new_trips)
    logger.info("User %s deleted trip %s", user_id, trip_id)
    return True


def update_trip(user_id: int, trip_id: str, updates: dict) -> dict | None:
    """Update fields of an existing trip. Returns updated trip or None."""
    trips = load_trips(user_id)
    for trip in trips:
        if trip["id"] == trip_id:
            trip.update(updates)
            save_trips(user_id, trips)
            logger.info("User %s updated trip %s: %s", user_id, trip_id, list(updates.keys()))
            return trip
    return None


def remove_city_from_trip(user_id: int, trip_id: str, city_index: int) -> dict | None:
    """Remove a city by index from a trip. Returns updated trip or None."""
    trips = load_trips(user_id)
    for trip in trips:
        if trip["id"] == trip_id:
            cities = trip.get("cities", [])
            if 0 <= city_index < len(cities):
                removed = cities.pop(city_index)
                save_trips(user_id, trips)
                logger.info("User %s removed city %s from trip %s", user_id, removed.get("name"), trip_id)
                return trip
    return None
