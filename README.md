# Trippa

Telegram-бот и PWA для планирования поездок.

## Структура проекта

```
bot/            Telegram-бот + REST API + Mini App
static-site/    PWA-сайт (nginx + service worker)
```

## Бот

Управление поездками через Telegram: создание, редактирование, удаление, голосовые сообщения, напоминания.

**Команды:** `/start`, `/new`, `/list`, `/edit`, `/delete`, `/help`, `/cancel`, `/test_remind`

**Голосовые сообщения** — отправьте голосовое, бот распознает речь (Whisper) и создаст поездку автоматически (GPT-4o-mini).

**Напоминания** — ежедневно в 22:00 МСК за 7 и 1 день до поездки.

**Mini App** — веб-интерфейс внутри Telegram с REST API.

Подробнее: [bot/README.md](bot/README.md)

## PWA-сайт

Статический сайт с тёмной темой, офлайн-поддержкой (service worker) и установкой на домашний экран.

Деплой: Docker (nginx:alpine) на Railway.

## Запуск

### Бот

```bash
cd bot
pip install -r requirements.txt
export TRIPPA_BOT_TOKEN="your-token"
export OPENAI_API_KEY="your-key"      # для голосовых сообщений
python main.py
```

### Сайт

```bash
cd static-site
docker build -t trippa-site .
docker run -e PORT=8080 -p 8080:8080 trippa-site
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `TRIPPA_BOT_TOKEN` | Токен Telegram бота | — |
| `OPENAI_API_KEY` | Ключ OpenAI (Whisper + GPT) | — |
| `TRIPPA_DATA_DIR` | Папка хранения данных | `bot/data/` |
| `PORT` / `WEB_PORT` | Порт веб-сервера | `8080` |
