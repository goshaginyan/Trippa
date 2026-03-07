#!/usr/bin/env python3
"""Trippa Telegram Bot — manage travel plans from Telegram."""

import logging
from datetime import datetime, date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN
import storage

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

EMOJI = {
    "vacation": "\U0001f334",
    "business": "\U0001f4bc",
    "weekend": "\u26fa",
    "trip": "\U0001f697",
    "other": "\U0001f4cc",
}

TYPE_LABELS = {
    "vacation": "Отпуск",
    "business": "Командировка",
    "weekend": "Выходные",
    "trip": "Поездка",
    "other": "Другое",
}

# Conversation states
NAME, TYPE, CITY_NAME, CITY_FROM, CITY_TO, MORE_CITIES = range(6)


# ── Helpers ──────────────────────────────────────────────────────────────

def fmt_date(ds: str) -> str:
    if not ds:
        return ""
    try:
        d = datetime.strptime(ds, "%Y-%m-%d")
        return d.strftime("%d.%m.%y")
    except ValueError:
        return ds


def fmt_trip(tr: dict) -> str:
    emoji = EMOJI.get(tr["type"], "")
    label = TYPE_LABELS.get(tr["type"], tr["type"])
    lines = [f"{emoji} *{_escape(tr['name'])}*  _{_escape(label)}_"]

    for c in tr.get("cities", []):
        lines.append(
            f"  • {_escape(c['name'])}  {fmt_date(c['dateFrom'])} — {fmt_date(c['dateTo'])}"
        )

    cities = tr.get("cities", [])
    if cities:
        first_date = cities[0].get("dateFrom", "")
        last_date = cities[-1].get("dateTo", "")
        try:
            first = datetime.strptime(first_date, "%Y-%m-%d").date()
            last = datetime.strptime(last_date, "%Y-%m-%d").date()
            today = date.today()
            if today > last:
                lines.append("  📦 _В архиве_")
            elif today >= first:
                lines.append("  ✈️ _Сейчас в поездке\\!_")
            else:
                diff = (first - today).days
                lines.append(f"  ⏳ _Через {diff} дн\\._")
        except ValueError:
            pass

    return "\n".join(lines)


def _escape(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    special = r"_*[]()~`>#+-=|{}.!"
    result = []
    for ch in text:
        if ch in special:
            result.append(f"\\{ch}")
        else:
            result.append(ch)
    return "".join(result)


# ── Command Handlers ─────────────────────────────────────────────────────

async def cmd_start(update: Update, context) -> None:
    await update.message.reply_text(
        "🌍 *Trippa* — бот для планирования поездок\\!\n\n"
        "Команды:\n"
        "/new — новая поездка\n"
        "/trips — список поездок\n"
        "/delete — удалить поездку\n"
        "/help — справка",
        parse_mode="MarkdownV2",
    )


async def cmd_help(update: Update, context) -> None:
    await update.message.reply_text(
        "📖 *Как пользоваться Trippa Bot*\n\n"
        "/new — создать поездку пошагово\n"
        "/trips — показать все поездки\n"
        "/delete — удалить поездку\n\n"
        "При создании поездки бот спросит:\n"
        "1\\. Название\n"
        "2\\. Тип \\(отпуск, командировка\\.\\.\\.\\)\n"
        "3\\. Города с датами\n\n"
        "Даты вводите в формате *ДД\\.ММ\\.ГГГГ* или *ГГГГ\\-ММ\\-ДД*",
        parse_mode="MarkdownV2",
    )


async def cmd_trips(update: Update, context) -> None:
    user_id = update.effective_user.id
    trips = storage.load_trips(user_id)
    if not trips:
        await update.message.reply_text("У вас пока нет поездок. Создайте первую: /new")
        return

    today = date.today()
    upcoming = []
    archive = []

    for tr in trips:
        cities = tr.get("cities", [])
        if not cities:
            archive.append(tr)
            continue
        try:
            last = datetime.strptime(cities[-1]["dateTo"], "%Y-%m-%d").date()
            if last < today:
                archive.append(tr)
            else:
                upcoming.append(tr)
        except (ValueError, KeyError):
            archive.append(tr)

    upcoming.sort(
        key=lambda t: t.get("cities", [{}])[0].get("dateFrom", "9999-99-99")
    )

    parts = []
    if upcoming:
        parts.append("📋 *Предстоящие:*\n")
        for tr in upcoming:
            parts.append(fmt_trip(tr))
            parts.append("")

    if archive:
        parts.append("📦 *Архив:*\n")
        for tr in archive:
            parts.append(fmt_trip(tr))
            parts.append("")

    await update.message.reply_text("\n".join(parts), parse_mode="MarkdownV2")


# ── New Trip Conversation ────────────────────────────────────────────────

async def new_start(update: Update, context) -> int:
    context.user_data["new_trip"] = {"cities": []}
    await update.message.reply_text("✏️ Введите название поездки:")
    return NAME


async def new_name(update: Update, context) -> int:
    context.user_data["new_trip"]["name"] = update.message.text.strip()

    keyboard = [
        [
            InlineKeyboardButton(f"{EMOJI['vacation']} Отпуск", callback_data="type:vacation"),
            InlineKeyboardButton(f"{EMOJI['business']} Командировка", callback_data="type:business"),
        ],
        [
            InlineKeyboardButton(f"{EMOJI['weekend']} Выходные", callback_data="type:weekend"),
            InlineKeyboardButton(f"{EMOJI['trip']} Поездка", callback_data="type:trip"),
        ],
        [
            InlineKeyboardButton(f"{EMOJI['other']} Другое", callback_data="type:other"),
        ],
    ]
    await update.message.reply_text(
        "Выберите тип:", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TYPE


async def new_type(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    trip_type = query.data.split(":")[1]
    context.user_data["new_trip"]["type"] = trip_type
    label = TYPE_LABELS.get(trip_type, trip_type)
    await query.edit_message_text(f"Тип: {EMOJI.get(trip_type, '')} {label}")
    await query.message.reply_text("🏙 Введите название города:")
    return CITY_NAME


async def new_city_name(update: Update, context) -> int:
    city = {"name": update.message.text.strip()}
    context.user_data["current_city"] = city
    await update.message.reply_text(
        "📅 Дата заезда (ДД.ММ.ГГГГ или ГГГГ-ММ-ДД):"
    )
    return CITY_FROM


def parse_date(text: str) -> str | None:
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = datetime.strptime(text, fmt)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


async def new_city_from(update: Update, context) -> int:
    ds = parse_date(update.message.text)
    if not ds:
        await update.message.reply_text("❌ Неверный формат даты. Попробуйте ДД.ММ.ГГГГ:")
        return CITY_FROM
    context.user_data["current_city"]["dateFrom"] = ds
    await update.message.reply_text("📅 Дата выезда (ДД.ММ.ГГГГ или ГГГГ-ММ-ДД):")
    return CITY_TO


async def new_city_to(update: Update, context) -> int:
    ds = parse_date(update.message.text)
    if not ds:
        await update.message.reply_text("❌ Неверный формат даты. Попробуйте ДД.ММ.ГГГГ:")
        return CITY_TO

    city = context.user_data["current_city"]
    city["dateTo"] = ds
    context.user_data["new_trip"]["cities"].append(city)

    keyboard = [
        [
            InlineKeyboardButton("➕ Добавить ещё город", callback_data="more:yes"),
            InlineKeyboardButton("✅ Сохранить", callback_data="more:no"),
        ]
    ]
    cities = context.user_data["new_trip"]["cities"]
    route = " → ".join(c["name"] for c in cities)
    await update.message.reply_text(
        f"Маршрут: {route}\n\nДобавить ещё город?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return MORE_CITIES


async def new_more_cities(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":")[1]

    if choice == "yes":
        await query.edit_message_text(query.message.text)
        await query.message.reply_text("🏙 Введите название города:")
        return CITY_NAME

    # Save trip
    data = context.user_data["new_trip"]
    user_id = update.effective_user.id
    trip = storage.add_trip(
        user_id=user_id,
        name=data["name"],
        trip_type=data["type"],
        cities=data["cities"],
    )

    await query.edit_message_text(query.message.text)
    await query.message.reply_text(
        f"✅ Поездка сохранена!\n\n{fmt_trip(trip)}",
        parse_mode="MarkdownV2",
    )
    context.user_data.pop("new_trip", None)
    context.user_data.pop("current_city", None)
    return ConversationHandler.END


async def new_cancel(update: Update, context) -> int:
    context.user_data.pop("new_trip", None)
    context.user_data.pop("current_city", None)
    await update.message.reply_text("❌ Создание поездки отменено.")
    return ConversationHandler.END


# ── Delete Trip ──────────────────────────────────────────────────────────

async def cmd_delete(update: Update, context) -> None:
    user_id = update.effective_user.id
    trips = storage.load_trips(user_id)
    if not trips:
        await update.message.reply_text("У вас нет поездок.")
        return

    keyboard = []
    for tr in trips:
        emoji = EMOJI.get(tr["type"], "")
        label = f"{emoji} {tr['name']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"del:{tr['id']}")])

    await update.message.reply_text(
        "Какую поездку удалить?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def delete_callback(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    trip_id = query.data.split(":")[1]
    user_id = update.effective_user.id

    if storage.delete_trip(user_id, trip_id):
        await query.edit_message_text("🗑 Поездка удалена.")
    else:
        await query.edit_message_text("Поездка не найдена.")


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        logger.error("TRIPPA_BOT_TOKEN environment variable is not set!")
        raise SystemExit(1)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Conversation for creating new trip
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("new", new_start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_name)],
            TYPE: [CallbackQueryHandler(new_type, pattern=r"^type:")],
            CITY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_city_name)],
            CITY_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_city_from)],
            CITY_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_city_to)],
            MORE_CITIES: [CallbackQueryHandler(new_more_cities, pattern=r"^more:")],
        },
        fallbacks=[CommandHandler("cancel", new_cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("trips", cmd_trips))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CallbackQueryHandler(delete_callback, pattern=r"^del:"))

    logger.info("Trippa bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
