# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
pip install -r requirements.txt
export TRIPPA_BOT_TOKEN="your-token-here"
python main.py
```

The bot reads `.env` file automatically via `config.py` (no dotenv dependency). Set `TRIPPA_BOT_TOKEN` there or as an env var.

## Architecture

Telegram bot for managing travel plans ("trips"), built with `python-telegram-bot` v21.6.

**Three files, single process:**

- **main.py** — All handlers, keyboards, calendar widget, and conversation flow. Uses `ConversationHandler` with 7 states: `TYPE → NAME → CITY_PICK → CITY_NAME → CITY_FROM → CITY_TO → MORE_CITIES` (order matches web UI). Commands (`/start`, `/new`, `/trips`, `/delete`, `/help`, `/cancel`) are also accessible via `ReplyKeyboardMarkup` buttons. Fallback handlers allow commands to work mid-conversation by ending the conversation first.
- **config.py** — Loads `.env` manually (no third-party lib), exports `BOT_TOKEN` and `DATA_DIR`.
- **storage.py** — Per-user JSON file storage in `DATA_DIR` (default: `bot/data/`). Each user gets `{user_id}.json` containing a list of trip dicts.

**Trip data shape:**
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
- Inline calendar widget (`DatePicker` from `datepicker.py`) uses callback data format `{prefix}:{action}:{year}:{month}:{day}`
- Callback data prefixes: `type:`, `city:`, `from:`, `to:`, `more:`, `del:`, `efrom:`, `eto:`, `eafrom:`, `eato:`
- UI language is Russian
