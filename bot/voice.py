"""Voice message processing: Whisper STT + GPT structured extraction."""

import io
import json
import logging
from datetime import date

from openai import AsyncOpenAI

from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

TRIP_SYSTEM_PROMPT = f"""\
Ты — помощник для планирования поездок. Из текста пользователя извлеки:
- type: один из vacation, business, weekend, trip, other
- name: название поездки (придумай короткое если не указано)
- cities: массив городов с датами [{{"name": "...", "dateFrom": "YYYY-MM-DD", "dateTo": "YYYY-MM-DD"}}]

Сегодня {date.today().isoformat()}. Если год не указан, используй ближайшую будущую дату.
Если указан только один день для города — dateFrom и dateTo совпадают.
Если даты не указаны совсем — оставь cities пустым массивом.

Ответь ТОЛЬКО валидным JSON без markdown-обёртки."""


async def transcribe(voice_bytes: bytes, filename: str = "voice.ogg") -> str | None:
    """Transcribe audio bytes via Whisper API. Returns text or None."""
    if not _client:
        return None
    buf = io.BytesIO(voice_bytes)
    buf.name = filename
    resp = await _client.audio.transcriptions.create(
        model="whisper-1",
        file=buf,
        language="ru",
    )
    text = resp.text.strip()
    logger.info("Whisper transcription: %s", text)
    return text


async def parse_trip(text: str) -> dict | None:
    """Extract trip data from natural language text. Returns dict or None."""
    if not _client:
        return None
    resp = await _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": TRIP_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0,
    )
    raw = resp.choices[0].message.content.strip()
    logger.info("GPT parse_trip raw: %s", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to parse GPT response as JSON")
        return None
    if not isinstance(data, dict):
        return None
    if "type" not in data or "name" not in data:
        return None
    return data
