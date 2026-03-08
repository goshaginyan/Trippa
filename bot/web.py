"""HTTP API for Trippa — serves trips to the Telegram Mini App.

Validates Telegram initData via HMAC-SHA256, then proxies CRUD to storage.
Runs alongside the bot in the same async loop.
"""

import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
from urllib.parse import parse_qs

from aiohttp import web

import storage

logger = logging.getLogger(__name__)


# ── Telegram initData validation ─────────────────────────────────────

def _validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Validate Telegram Web App initData and return parsed data.

    Returns the parsed data dict (including 'user') on success, None on failure.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        data_dict = {k: v[0] for k, v in parsed.items()}
    except Exception:
        return None

    received_hash = data_dict.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(data_dict.items())
    )

    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()

    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    user_raw = data_dict.get("user")
    if user_raw:
        try:
            data_dict["user"] = json.loads(user_raw)
        except (json.JSONDecodeError, TypeError):
            return None

    return data_dict


# ── Auth middleware ───────────────────────────────────────────────────

def _make_auth_middleware(bot_token: str):
    @web.middleware
    async def auth_middleware(request: web.Request, handler):
        if request.method == "OPTIONS":
            return await handler(request)

        if not request.path.startswith("/api/"):
            return await handler(request)

        init_data = request.headers.get("X-Telegram-Init-Data", "")
        if not init_data:
            raise web.HTTPUnauthorized(text="Missing initData")

        validated = _validate_init_data(init_data, bot_token)
        if validated is None:
            raise web.HTTPUnauthorized(text="Invalid initData")

        user = validated.get("user")
        if not user or "id" not in user:
            raise web.HTTPUnauthorized(text="No user in initData")

        request["user_id"] = int(user["id"])
        return await handler(request)

    return auth_middleware


# ── CORS middleware ──────────────────────────────────────────────────

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Telegram-Init-Data",
    "Access-Control-Max-Age": "86400",
}


@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=CORS_HEADERS)
    response = await handler(request)
    response.headers.update(CORS_HEADERS)
    return response


# ── Route handlers ───────────────────────────────────────────────────

async def list_trips(request: web.Request) -> web.Response:
    user_id = request["user_id"]
    trips = storage.load_trips(user_id)
    return web.json_response(trips)


async def create_trip(request: web.Request) -> web.Response:
    user_id = request["user_id"]
    try:
        body = await request.json()
    except (json.JSONDecodeError, Exception):
        raise web.HTTPBadRequest(text="Invalid JSON")

    name = body.get("name", "").strip()
    trip_type = body.get("type", "other")
    cities = body.get("cities", [])
    notif_days = body.get("notifDays", 1)

    if not name:
        raise web.HTTPBadRequest(text="Missing required field: name")

    valid_types = ("vacation", "business", "weekend", "trip", "other")
    if trip_type not in valid_types:
        raise web.HTTPBadRequest(text="Invalid type")

    if not isinstance(cities, list) or not cities:
        raise web.HTTPBadRequest(text="At least one city is required")

    for city in cities:
        if not isinstance(city, dict):
            raise web.HTTPBadRequest(text="Invalid city format")
        if not city.get("name") or not city.get("dateFrom") or not city.get("dateTo"):
            raise web.HTTPBadRequest(text="Each city must have name, dateFrom, dateTo")

    trip = storage.add_trip(user_id, name, trip_type, cities, notif_days)
    return web.json_response(trip, status=201)


async def update_trip(request: web.Request) -> web.Response:
    user_id = request["user_id"]
    trip_id = request.match_info["id"]

    try:
        body = await request.json()
    except (json.JSONDecodeError, Exception):
        raise web.HTTPBadRequest(text="Invalid JSON")

    updates = {}
    if "name" in body:
        name = body["name"].strip()
        if not name:
            raise web.HTTPBadRequest(text="Name cannot be empty")
        updates["name"] = name
    if "type" in body:
        valid_types = ("vacation", "business", "weekend", "trip", "other")
        if body["type"] not in valid_types:
            raise web.HTTPBadRequest(text="Invalid type")
        updates["type"] = body["type"]
    if "cities" in body:
        if not isinstance(body["cities"], list) or not body["cities"]:
            raise web.HTTPBadRequest(text="At least one city is required")
        updates["cities"] = body["cities"]
    if "notifDays" in body:
        updates["notifDays"] = body["notifDays"]
    if "isPublic" in body:
        updates["isPublic"] = bool(body["isPublic"])

    if not updates:
        raise web.HTTPBadRequest(text="No fields to update")

    trip = storage.update_trip(user_id, trip_id, updates)
    if trip is None:
        raise web.HTTPNotFound(text="Trip not found")

    return web.json_response(trip)


async def delete_trip(request: web.Request) -> web.Response:
    user_id = request["user_id"]
    trip_id = request.match_info["id"]

    if not storage.delete_trip(user_id, trip_id):
        raise web.HTTPNotFound(text="Trip not found")

    return web.json_response({"ok": True})


# ── Mini App static serving ──────────────────────────────────────────

MINIAPP_DIR = Path(__file__).parent / "miniapp"


async def serve_miniapp(request: web.Request) -> web.FileResponse:
    return web.FileResponse(MINIAPP_DIR / "index.html")


# ── App factory ──────────────────────────────────────────────────────

def create_app(bot_token: str) -> web.Application:
    app = web.Application(middlewares=[
        cors_middleware,
        _make_auth_middleware(bot_token),
    ])
    app.router.add_get("/", serve_miniapp)
    app.router.add_get("/api/trips", list_trips)
    app.router.add_post("/api/trips", create_trip)
    app.router.add_put("/api/trips/{id}", update_trip)
    app.router.add_delete("/api/trips/{id}", delete_trip)
    return app
