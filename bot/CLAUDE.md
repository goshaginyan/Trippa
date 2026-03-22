# CLAUDE.md

Guidance for Claude Code when working with this repository.

## Running the Bot

```bash
pip install -r requirements.txt
export TRIPPA_BOT_TOKEN="your-token"
export OPENAI_API_KEY="your-key"
python main.py
```

The bot reads `.env` file automatically via `config.py` (no dotenv dependency). Set variables there or as env vars.

## Architecture

Telegram bot for managing travel plans ("trips"), built with `python-telegram-bot` v21.6 + aiohttp.

**Single process, two servers:** Telegram bot (polling) and aiohttp web server run in the same async event loop.

### Files

- **main.py** — All handlers, keyboards, calendar widget, conversation flows, reminders, voice handler. Uses `ConversationHandler` with 16 states across three flows: create, edit, edit-add. Commands (`/start`, `/new`, `/list`, `/edit`, `/delete`, `/help`, `/cancel`, `/test_remind`) are also accessible via `ReplyKeyboardMarkup` buttons. Fallback handlers allow commands mid-conversation.
- **config.py** — Loads `.env` manually (no third-party lib), exports `BOT_TOKEN`, `DATA_DIR`, `OPENAI_API_KEY`.
- **storage.py** — Per-user JSON file storage in `DATA_DIR` (default: `bot/data/`). Each user gets `{user_id}.json` with a list of trip dicts. Functions: `load_trips`, `save_trips`, `add_trip`, `delete_trip`, `update_trip`, `all_user_ids`.
- **voice.py** — OpenAI integration: `transcribe()` calls Whisper API (Russian), `parse_trip()` calls GPT-4o-mini to extract structured trip data from text. Strips markdown code blocks from GPT responses.
- **datepicker.py** — Reusable `DatePicker` class for inline calendar widgets. Russian month/weekday names. Used with 6 different prefixes for create/edit flows.
- **web.py** — REST API (`/api/trips` CRUD) with Telegram Mini App initData validation (HMAC-SHA256). CORS enabled. Serves `miniapp/index.html` at `/`.
- **miniapp/index.html** — Telegram Mini App UI: dark theme, trip CRUD via REST API.

### Conversation States (16)

Create: `TYPE → NAME → CITY_PICK → CITY_NAME → CITY_FROM → CITY_TO → MORE_CITIES`

Edit: `EDIT_CITIES → EDIT_ACTION → EDIT_CITY_NAME → EDIT_CITY_FROM → EDIT_CITY_TO`

Edit-add: `EDIT_ADD_PICK → EDIT_ADD_NAME → EDIT_ADD_FROM → EDIT_ADD_TO`

### Trip Data Shape

```json
{
  "id": "hex-timestamp+random",
  "name": "string",
  "type": "vacation|business|weekend|trip|other",
  "cities": [{"name": "string", "dateFrom": "YYYY-MM-DD", "dateTo": "YYYY-MM-DD"}],
  "notifDays": 1
}
```

## Key Patterns

- All bot messages use HTML parse mode — escape user text with `_html()` helper
- Inline calendar widget (`DatePicker`) uses callback data format `{prefix}:{action}:{year}:{month}:{day}`
- Callback data prefixes: `type:`, `city:`, `from:`, `to:`, `more:`, `del:`, `delconfirm:`, `edit:`, `ecity:`, `eact:`, `eacity:`, `efrom:`, `eto:`, `eafrom:`, `eato:`
- UI language is Russian throughout (messages, calendar, buttons)
- Reminders run daily at 22:00 MSK via job queue, check all users for trips starting in 7 or 1 day
- Voice flow: audio bytes → Whisper transcription → GPT-4o-mini JSON extraction → `add_trip()`
- Mini App auth: Telegram initData validated via HMAC-SHA256 in middleware

## Static Site

`static-site/` contains a standalone PWA (nginx:alpine Docker image):
- `index.html` — dark-themed trip viewer, offline-capable
- `sw.js` — service worker for caching
- `manifest.json` — PWA manifest (standalone display)
- Deployed on Railway, nginx listens on `$PORT`

## Linting

```bash
# Python
ruff check bot/
# or
flake8 bot/
```
