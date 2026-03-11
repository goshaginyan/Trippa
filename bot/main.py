#!/usr/bin/env python3
"""Trippa Telegram Bot — manage travel plans from Telegram."""

import asyncio
import logging
import os
from datetime import datetime, date, time as dt_time, timezone, timedelta

from aiohttp import web
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    BotCommand,
    MenuButtonCommands,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN
from datepicker import DatePicker
import storage
import voice
from web import create_app

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

POPULAR_CITIES = [
    "Москва", "Санкт-Петербург", "Стамбул", "Париж",
    "Рим", "Барселона", "Дубай", "Бангкок",
    "Тбилиси", "Ереван", "Бали", "Лондон",
]

NAME_TEMPLATES = {
    "vacation": ["Отпуск в Европе", "Отпуск на море", "Отпуск в горах"],
    "business": ["Командировка в Москву", "Бизнес-поездка", "Конференция"],
    "weekend": ["Выходные за городом", "Уикенд в Питере", "Короткий выезд"],
    "trip": ["Поездка по России", "Автопутешествие", "Поездка к друзьям"],
    "other": ["Переезд", "Свадьба", "Фестиваль"],
}

# ── Button labels (used for ReplyKeyboard and matching) ──────────────────
BTN_NEW = "➕ Новая поездка"
BTN_LIST = "📋 Все поездки"
BTN_EDIT = "✏️ Редактировать"
BTN_DELETE = "🗑 Удалить"
BTN_HELP = "❓ Помощь"
BTN_CANCEL = "❌ Отмена"

# Conversation states
(TYPE, NAME, CITY_PICK, CITY_NAME, CITY_FROM, CITY_TO, MORE_CITIES,
 EDIT_CITIES, EDIT_ACTION, EDIT_CITY_NAME, EDIT_CITY_FROM, EDIT_CITY_TO,
 EDIT_ADD_PICK, EDIT_ADD_NAME, EDIT_ADD_FROM, EDIT_ADD_TO) = range(16)


# ── Keyboards ────────────────────────────────────────────────────────────

def main_keyboard() -> ReplyKeyboardMarkup:
    """Persistent main menu keyboard at the bottom of the chat."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_NEW)],
            [KeyboardButton(BTN_LIST), KeyboardButton(BTN_EDIT)],
            [KeyboardButton(BTN_DELETE), KeyboardButton(BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard shown during conversation with only Cancel button."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_CANCEL)]],
        resize_keyboard=True,
    )


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
    name = _html(tr["name"])
    lines = [f"{emoji} <b>{name}</b>  <i>{_html(label)}</i>"]

    for c in tr.get("cities", []):
        lines.append(
            f"  • {_html(c['name'])}  {fmt_date(c['dateFrom'])} — {fmt_date(c['dateTo'])}"
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
                lines.append("  📦 <i>В архиве</i>")
            elif today >= first:
                lines.append("  ✈️ <i>Сейчас в поездке!</i>")
            else:
                diff = (first - today).days
                lines.append(f"  ⏳ <i>Через {diff} дн.</i>")
        except ValueError:
            pass

    return "\n".join(lines)


def _html(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Date pickers ─────────────────────────────────────────────────────────
_from_picker = DatePicker(prefix="from", show_year=True)
_to_picker = DatePicker(prefix="to", show_year=True)
_efrom_picker = DatePicker(prefix="efrom", show_year=True)
_eto_picker = DatePicker(prefix="eto", show_year=True)
_eafrom_picker = DatePicker(prefix="eafrom", show_year=True)
_eato_picker = DatePicker(prefix="eato", show_year=True)


# ── Command Handlers ─────────────────────────────────────────────────────

async def cmd_start(update: Update, context) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"🌍 Привет, {_html(user.first_name)}!\n\n"
        "<b>Trippa</b> — бот для планирования поездок.\n\n"
        "Используй кнопки внизу или команды:\n"
        f"  {BTN_NEW} — создать поездку\n"
        f"  {BTN_LIST} — посмотреть поездки\n"
        f"  {BTN_EDIT} — редактировать поездку\n"
        f"  {BTN_DELETE} — удалить поездку\n"
        f"  {BTN_HELP} — справка",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


async def cmd_help(update: Update, context) -> None:
    await update.message.reply_text(
        "📖 <b>Как пользоваться Trippa Bot</b>\n\n"
        f"<b>{BTN_NEW}</b> или /new — создать поездку пошагово\n"
        f"<b>{BTN_LIST}</b> или /list — показать все поездки\n"
        f"<b>{BTN_EDIT}</b> или /edit — редактировать поездку\n"
        f"<b>{BTN_DELETE}</b> или /delete — удалить поездку\n\n"
        "При создании поездки:\n"
        "1. Выберите тип (отпуск, командировка...)\n"
        "2. Введите название\n"
        "3. Выберите город из списка или введите свой\n"
        "4. Выберите даты в календаре\n\n"
        f"Нажмите <b>{BTN_CANCEL}</b> чтобы отменить создание.",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


async def cmd_list(update: Update, context) -> None:
    user_id = update.effective_user.id
    trips = storage.load_trips(user_id)
    if not trips:
        await update.message.reply_text(
            "У вас пока нет поездок.\n\nНажмите <b>➕ Новая поездка</b> чтобы создать первую!",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )
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

    # Send each trip as a separate message with its own delete/edit button
    if upcoming:
        await update.message.reply_text(
            "📋 <b>Предстоящие:</b>", parse_mode="HTML",
            reply_markup=main_keyboard(),
        )
        for tr in upcoming:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit:{tr['id']}"),
                InlineKeyboardButton("🗑 Удалить", callback_data=f"del:{tr['id']}"),
            ]])
            await update.message.reply_text(
                fmt_trip(tr), parse_mode="HTML", reply_markup=kb,
            )

    if archive:
        await update.message.reply_text(
            "📦 <b>Архив:</b>", parse_mode="HTML",
            reply_markup=main_keyboard() if not upcoming else None,
        )
        for tr in archive:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit:{tr['id']}"),
                InlineKeyboardButton("🗑 Удалить", callback_data=f"del:{tr['id']}"),
            ]])
            await update.message.reply_text(
                fmt_trip(tr), parse_mode="HTML", reply_markup=kb,
            )


# ── New Trip Conversation ────────────────────────────────────────────────

async def new_start(update: Update, context) -> int:
    context.user_data["new_trip"] = {"cities": []}
    await update.message.reply_text("➕ Создание поездки", reply_markup=cancel_keyboard())
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
        "Выберите тип поездки:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return TYPE


async def new_type(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    trip_type = query.data.split(":")[1]
    context.user_data["new_trip"]["type"] = trip_type
    label = TYPE_LABELS.get(trip_type, trip_type)
    await query.edit_message_text(f"Тип: {EMOJI.get(trip_type, '')} {label}")

    templates = NAME_TEMPLATES.get(trip_type, [])
    hint = ", ".join(f"«{t}»" for t in templates)
    await query.message.reply_text(
        f"✏️ Введите название поездки:\n\n💡 Например: {hint}",
        reply_markup=cancel_keyboard(),
    )
    return NAME


async def new_name(update: Update, context) -> int:
    context.user_data["new_trip"]["name"] = update.message.text.strip()
    await _send_city_picker(update.message, context)
    return CITY_PICK


async def _send_city_picker(message, context) -> None:
    """Send popular cities keyboard."""
    rows = []
    for i in range(0, len(POPULAR_CITIES), 3):
        row = [
            InlineKeyboardButton(city, callback_data=f"city:{city}")
            for city in POPULAR_CITIES[i:i + 3]
        ]
        rows.append(row)
    rows.append([InlineKeyboardButton("✍️ Ввести вручную", callback_data="city:__custom__")])
    await message.reply_text(
        "🏙 Выберите город или введите вручную:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def new_city_pick(update: Update, context) -> int:
    """Handle city selection from popular list."""
    query = update.callback_query
    await query.answer()
    city_name = query.data.split(":", 1)[1]

    if city_name == "__custom__":
        await query.edit_message_text("🏙 Введите название города:")
        return CITY_NAME

    context.user_data["current_city"] = {"name": city_name}
    await query.edit_message_text(f"🏙 Город: {city_name}")
    await _send_calendar(query.message, context, _from_picker, "📅 Дата заезда:")
    return CITY_FROM


async def new_city_name(update: Update, context) -> int:
    city = {"name": update.message.text.strip()}
    context.user_data["current_city"] = city
    await _send_calendar(update.message, context, _from_picker, "📅 Дата заезда:")
    return CITY_FROM


async def _send_calendar(message, context, picker: DatePicker, text: str) -> None:
    """Send calendar for date selection starting from current month."""
    today = date.today()
    kb = picker.build(today.year, today.month)
    await message.reply_text(text, reply_markup=kb)


def parse_date(text: str) -> str | None:
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = datetime.strptime(text, fmt)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


async def cal_from_callback(update: Update, context) -> int:
    """Handle calendar navigation and day selection for dateFrom."""
    query = update.callback_query
    await query.answer()
    result = _from_picker.parse(query.data)

    if result[0] == "noop":
        return CITY_FROM

    if result[0] == "navigate":
        _, year, month = result
        kb = _from_picker.build(year, month)
        await query.edit_message_reply_markup(reply_markup=kb)
        return CITY_FROM

    if result[0] == "day":
        _, year, month, day = result
        ds = f"{year}-{month:02d}-{day:02d}"
        context.user_data["current_city"]["dateFrom"] = ds
        d = date(year, month, day)
        await query.edit_message_text(f"📅 Заезд: {d.strftime('%d.%m.%Y')}")
        await _send_calendar(query.message, context, _to_picker, "📅 Дата выезда:")
        return CITY_TO

    return CITY_FROM


async def new_city_from(update: Update, context) -> int:
    """Handle manual text date input for dateFrom."""
    logger.warning("new_city_from received text: %r", update.message.text)
    ds = parse_date(update.message.text)
    if not ds:
        await update.message.reply_text("❌ Неверный формат даты. Попробуйте ДД.ММ.ГГГГ:")
        return CITY_FROM
    context.user_data["current_city"]["dateFrom"] = ds
    await _send_calendar(update.message, context, _to_picker, "📅 Дата выезда:")
    return CITY_TO


async def cal_to_callback(update: Update, context) -> int:
    """Handle calendar navigation and day selection for dateTo."""
    query = update.callback_query
    await query.answer()
    result = _to_picker.parse(query.data)

    if result[0] == "noop":
        return CITY_TO

    if result[0] == "navigate":
        _, year, month = result
        kb = _to_picker.build(year, month)
        await query.edit_message_reply_markup(reply_markup=kb)
        return CITY_TO

    if result[0] == "day":
        _, year, month, day = result
        ds = f"{year}-{month:02d}-{day:02d}"
        city = context.user_data["current_city"]
        city["dateTo"] = ds
        context.user_data["new_trip"]["cities"].append(city)

        d = date(year, month, day)
        await query.edit_message_text(f"📅 Выезд: {d.strftime('%d.%m.%Y')}")
        return await _ask_more_cities(query.message, context)

    return CITY_TO


async def new_city_to(update: Update, context) -> int:
    """Handle manual text date input for dateTo."""
    logger.warning("new_city_to received text: %r", update.message.text)
    ds = parse_date(update.message.text)
    if not ds:
        await update.message.reply_text("❌ Неверный формат даты. Попробуйте ДД.ММ.ГГГГ:")
        return CITY_TO

    city = context.user_data["current_city"]
    city["dateTo"] = ds
    context.user_data["new_trip"]["cities"].append(city)
    return await _ask_more_cities(update.message, context)


async def _ask_more_cities(message, context) -> int:
    """Ask if user wants to add more cities."""
    keyboard = [
        [
            InlineKeyboardButton("➕ Добавить ещё город", callback_data="more:yes"),
            InlineKeyboardButton("✅ Сохранить", callback_data="more:no"),
        ]
    ]
    cities = context.user_data["new_trip"]["cities"]
    route = " → ".join(c["name"] for c in cities)
    await message.reply_text(
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
        await _send_city_picker(query.message, context)
        return CITY_PICK

    # Save trip
    data = context.user_data["new_trip"]
    user_id = update.effective_user.id
    trip = storage.add_trip(
        user_id=user_id,
        name=data["name"],
        trip_type=data["type"],
        cities=data["cities"],
    )

    schedule_creation_reminder(context.application, user_id, trip)

    await query.edit_message_text(query.message.text)
    await query.message.reply_text(
        f"✅ Поездка сохранена!\n\n{fmt_trip(trip)}",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )
    context.user_data.pop("new_trip", None)
    context.user_data.pop("current_city", None)
    return ConversationHandler.END


async def new_cancel(update: Update, context) -> int:
    context.user_data.pop("new_trip", None)
    context.user_data.pop("current_city", None)
    await update.message.reply_text(
        "❌ Создание поездки отменено.",
        reply_markup=main_keyboard(),
    )
    return ConversationHandler.END


async def fallback_start(update: Update, context) -> int:
    """Handle /start while inside the conversation — reset and greet."""
    context.user_data.pop("new_trip", None)
    context.user_data.pop("current_city", None)
    await cmd_start(update, context)
    return ConversationHandler.END


async def fallback_help(update: Update, context) -> int:
    """Handle /help while inside the conversation — reset and show help."""
    context.user_data.pop("new_trip", None)
    context.user_data.pop("current_city", None)
    await cmd_help(update, context)
    return ConversationHandler.END


async def fallback_list(update: Update, context) -> int:
    """Handle /list while inside the conversation — reset and show trips."""
    context.user_data.pop("new_trip", None)
    context.user_data.pop("current_city", None)
    await cmd_list(update, context)
    return ConversationHandler.END


async def fallback_edit(update: Update, context) -> int:
    """Handle /edit while inside the conversation — reset and show edit."""
    context.user_data.pop("new_trip", None)
    context.user_data.pop("current_city", None)
    context.user_data.pop("edit_trip_id", None)
    context.user_data.pop("edit_city_idx", None)
    context.user_data.pop("edit_new_from", None)
    context.user_data.pop("edit_new_city", None)
    await cmd_edit(update, context)
    return ConversationHandler.END


async def fallback_delete(update: Update, context) -> int:
    """Handle /delete while inside the conversation — reset and show delete."""
    context.user_data.pop("new_trip", None)
    context.user_data.pop("current_city", None)
    context.user_data.pop("edit_trip_id", None)
    context.user_data.pop("edit_city_idx", None)
    context.user_data.pop("edit_new_from", None)
    context.user_data.pop("edit_new_city", None)
    await cmd_delete(update, context)
    return ConversationHandler.END


# ── Edit Trip ───────────────────────────────────────────────────────────

async def cmd_edit(update: Update, context) -> None:
    """Show list of trips to pick for editing."""
    user_id = update.effective_user.id
    trips = storage.load_trips(user_id)
    if not trips:
        await update.message.reply_text(
            "У вас нет поездок.", reply_markup=main_keyboard(),
        )
        return
    await update.message.reply_text("✏️ Редактирование", reply_markup=cancel_keyboard())
    keyboard = []
    for tr in trips:
        emoji = EMOJI.get(tr["type"], "")
        label = f"{emoji} {tr['name']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"edit:{tr['id']}")])
    await update.message.reply_text(
        "Выберите поездку:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def edit_start(update: Update, context) -> int:
    """Show field choices for the selected trip."""
    query = update.callback_query
    await query.answer()
    trip_id = query.data.split(":")[1]
    user_id = update.effective_user.id
    trips = storage.load_trips(user_id)
    trip = next((t for t in trips if t["id"] == trip_id), None)
    if not trip:
        await query.edit_message_text("Поездка не найдена.")
        return ConversationHandler.END

    context.user_data["edit_trip_id"] = trip_id
    await _send_edit_field_choices(query, trip)
    return EDIT_CITIES


async def _send_edit_field_choices(query, trip):
    """Show field choice buttons: name, cities/dates, add city."""
    emoji_icon = EMOJI.get(trip["type"], "")
    name = _html(trip["name"])
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Название", callback_data="ecity:editname")],
        [InlineKeyboardButton("🏙 Города и даты", callback_data="ecity:cities")],
        [InlineKeyboardButton("➕ Добавить город", callback_data="ecity:add")],
        [InlineKeyboardButton("✅ Готово", callback_data="ecity:done")],
    ])
    await query.edit_message_text(
        f"Редактировать: {emoji_icon} <b>{name}</b>",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def _send_edit_field_choices_msg(message, trip):
    """Show field choice buttons via new message."""
    emoji_icon = EMOJI.get(trip["type"], "")
    name = _html(trip["name"])
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Название", callback_data="ecity:editname")],
        [InlineKeyboardButton("🏙 Города и даты", callback_data="ecity:cities")],
        [InlineKeyboardButton("➕ Добавить город", callback_data="ecity:add")],
        [InlineKeyboardButton("✅ Готово", callback_data="ecity:done")],
    ])
    await message.reply_text(
        f"Редактировать: {emoji_icon} <b>{name}</b>",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def _send_edit_cities(query, context, trip):
    """Show city list with add/done buttons (edits existing message)."""
    rows = []
    for i, c in enumerate(trip.get("cities", [])):
        label = f"{c['name']}  {fmt_date(c['dateFrom'])} — {fmt_date(c['dateTo'])}"
        rows.append([InlineKeyboardButton(label, callback_data=f"ecity:{i}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="ecity:back")])

    emoji_icon = EMOJI.get(trip["type"], "")
    name = _html(trip["name"])
    await query.edit_message_text(
        f"Города: {emoji_icon} <b>{name}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def _send_edit_cities_msg(message, context, trip):
    """Show city list with add/done buttons (sends new message)."""
    rows = []
    for i, c in enumerate(trip.get("cities", [])):
        label = f"{c['name']}  {fmt_date(c['dateFrom'])} — {fmt_date(c['dateTo'])}"
        rows.append([InlineKeyboardButton(label, callback_data=f"ecity:{i}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="ecity:back")])

    emoji_icon = EMOJI.get(trip["type"], "")
    name = _html(trip["name"])
    await message.reply_text(
        f"Города: {emoji_icon} <b>{name}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def edit_city_pick(update: Update, context) -> int:
    """Handle city selection or add/done/editname/cities/back."""
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":")[1]

    user_id = update.effective_user.id
    trip_id = context.user_data["edit_trip_id"]

    if choice == "done":
        trips = storage.load_trips(user_id)
        trip = next((t for t in trips if t["id"] == trip_id), None)
        if trip:
            await query.edit_message_text(
                f"✅ Сохранено!\n\n{fmt_trip(trip)}", parse_mode="HTML",
            )
        else:
            await query.edit_message_text("Поездка не найдена.")
        context.user_data.pop("edit_trip_id", None)
        context.user_data.pop("edit_city_idx", None)
        return ConversationHandler.END

    if choice == "editname":
        await query.edit_message_text("📝 Введите новое название поездки:")
        return EDIT_CITY_NAME

    if choice == "cities":
        trips = storage.load_trips(user_id)
        trip = next((t for t in trips if t["id"] == trip_id), None)
        if not trip:
            await query.edit_message_text("Поездка не найдена.")
            return ConversationHandler.END
        await _send_edit_cities(query, context, trip)
        return EDIT_CITIES

    if choice == "back":
        trips = storage.load_trips(user_id)
        trip = next((t for t in trips if t["id"] == trip_id), None)
        if not trip:
            await query.edit_message_text("Поездка не найдена.")
            return ConversationHandler.END
        await _send_edit_field_choices(query, trip)
        return EDIT_CITIES

    if choice == "add":
        rows = []
        for i in range(0, len(POPULAR_CITIES), 3):
            row = [
                InlineKeyboardButton(city, callback_data=f"eacity:{city}")
                for city in POPULAR_CITIES[i:i + 3]
            ]
            rows.append(row)
        rows.append([InlineKeyboardButton("✍️ Ввести вручную", callback_data="eacity:__custom__")])
        await query.edit_message_text(
            "🏙 Выберите город или введите вручную:",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return EDIT_ADD_PICK

    # Numeric city index
    idx = int(choice)
    context.user_data["edit_city_idx"] = idx

    trips = storage.load_trips(user_id)
    trip = next((t for t in trips if t["id"] == trip_id), None)
    if not trip or idx >= len(trip["cities"]):
        await query.edit_message_text("Город не найден.")
        return ConversationHandler.END

    city = trip["cities"][idx]
    label = f"{_html(city['name'])}  {fmt_date(city['dateFrom'])} — {fmt_date(city['dateTo'])}"
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Название", callback_data="eact:name"),
            InlineKeyboardButton("📅 Даты", callback_data="eact:dates"),
        ],
        [InlineKeyboardButton("🗑 Удалить город", callback_data="eact:delete")],
    ])
    await query.edit_message_text(label, parse_mode="HTML", reply_markup=kb)
    return EDIT_ACTION


async def edit_action(update: Update, context) -> int:
    """Handle action choice for a city."""
    query = update.callback_query
    await query.answer()
    action = query.data.split(":")[1]
    user_id = update.effective_user.id
    trip_id = context.user_data["edit_trip_id"]
    idx = context.user_data["edit_city_idx"]

    if action == "name":
        context.user_data["_editing_city_name"] = True
        await query.edit_message_text("✏️ Введите новое название города:")
        return EDIT_CITY_NAME

    if action == "dates":
        await query.edit_message_text("📅 Выберите новую дату заезда:")
        today = date.today()
        kb = _efrom_picker.build(today.year, today.month)
        await query.message.reply_text("📅 Дата заезда:", reply_markup=kb)
        return EDIT_CITY_FROM

    if action == "delete":
        trips = storage.load_trips(user_id)
        trip = next((t for t in trips if t["id"] == trip_id), None)
        if not trip:
            await query.edit_message_text("Поездка не найдена.")
            return ConversationHandler.END

        if len(trip["cities"]) <= 1:
            storage.delete_trip(user_id, trip_id)
            await query.edit_message_text("🗑 Единственный город удалён — поездка удалена.")
            context.user_data.pop("edit_trip_id", None)
            context.user_data.pop("edit_city_idx", None)
            return ConversationHandler.END

        trip["cities"].pop(idx)
        storage.update_trip(user_id, trip_id, {"cities": trip["cities"]})
        trips = storage.load_trips(user_id)
        trip = next((t for t in trips if t["id"] == trip_id), None)
        await _send_edit_cities(query, context, trip)
        return EDIT_CITIES

    return EDIT_ACTION


async def edit_city_name(update: Update, context) -> int:
    """Handle new city name or trip name text input."""
    new_name = update.message.text.strip()
    user_id = update.effective_user.id
    trip_id = context.user_data["edit_trip_id"]
    idx = context.user_data.get("edit_city_idx")

    trips = storage.load_trips(user_id)
    trip = next((t for t in trips if t["id"] == trip_id), None)
    if not trip:
        await update.message.reply_text("Поездка не найдена.", reply_markup=main_keyboard())
        return ConversationHandler.END

    # If edit_city_idx is set and we came from eact:name, edit city name
    # If we came from ecity:editname, edit trip name
    if idx is not None and context.user_data.get("_editing_city_name"):
        if idx >= len(trip["cities"]):
            await update.message.reply_text("Город не найден.", reply_markup=main_keyboard())
            return ConversationHandler.END
        trip["cities"][idx]["name"] = new_name
        storage.update_trip(user_id, trip_id, {"cities": trip["cities"]})
        context.user_data.pop("_editing_city_name", None)
        trips = storage.load_trips(user_id)
        trip = next((t for t in trips if t["id"] == trip_id), None)
        await _send_edit_cities_msg(update.message, context, trip)
    else:
        # Editing trip name
        storage.update_trip(user_id, trip_id, {"name": new_name})
        trips = storage.load_trips(user_id)
        trip = next((t for t in trips if t["id"] == trip_id), None)
        await _send_edit_field_choices_msg(update.message, trip)

    return EDIT_CITIES


async def edit_cal_from(update: Update, context) -> int:
    """Handle calendar for editing dateFrom."""
    query = update.callback_query
    await query.answer()
    result = _efrom_picker.parse(query.data)

    if result[0] == "noop":
        return EDIT_CITY_FROM

    if result[0] == "navigate":
        _, year, month = result
        kb = _efrom_picker.build(year, month)
        await query.edit_message_reply_markup(reply_markup=kb)
        return EDIT_CITY_FROM

    if result[0] == "day":
        _, year, month, day = result
        ds = f"{year}-{month:02d}-{day:02d}"
        context.user_data["edit_new_from"] = ds
        d = date(year, month, day)
        await query.edit_message_text(f"📅 Заезд: {d.strftime('%d.%m.%Y')}")
        today = date.today()
        kb = _eto_picker.build(today.year, today.month)
        await query.message.reply_text("📅 Дата выезда:", reply_markup=kb)
        return EDIT_CITY_TO

    return EDIT_CITY_FROM


async def edit_city_from_text(update: Update, context) -> int:
    """Handle manual text date input for edit dateFrom."""
    logger.warning("edit_city_from_text received text: %r", update.message.text)
    ds = parse_date(update.message.text)
    if not ds:
        await update.message.reply_text("❌ Неверный формат даты. Попробуйте ДД.ММ.ГГГГ:")
        return EDIT_CITY_FROM
    context.user_data["edit_new_from"] = ds
    today = date.today()
    kb = _eto_picker.build(today.year, today.month)
    await update.message.reply_text("📅 Дата выезда:", reply_markup=kb)
    return EDIT_CITY_TO


async def edit_cal_to(update: Update, context) -> int:
    """Handle calendar for editing dateTo."""
    query = update.callback_query
    await query.answer()
    result = _eto_picker.parse(query.data)

    if result[0] == "noop":
        return EDIT_CITY_TO

    if result[0] == "navigate":
        _, year, month = result
        kb = _eto_picker.build(year, month)
        await query.edit_message_reply_markup(reply_markup=kb)
        return EDIT_CITY_TO

    if result[0] == "day":
        _, year, month, day = result
        ds = f"{year}-{month:02d}-{day:02d}"
        user_id = update.effective_user.id
        trip_id = context.user_data["edit_trip_id"]
        idx = context.user_data["edit_city_idx"]

        trips = storage.load_trips(user_id)
        trip = next((t for t in trips if t["id"] == trip_id), None)
        if not trip or idx >= len(trip["cities"]):
            await query.edit_message_text("Поездка не найдена.")
            return ConversationHandler.END

        trip["cities"][idx]["dateFrom"] = context.user_data["edit_new_from"]
        trip["cities"][idx]["dateTo"] = ds
        storage.update_trip(user_id, trip_id, {"cities": trip["cities"]})

        d = date(year, month, day)
        await query.edit_message_text(f"📅 Выезд: {d.strftime('%d.%m.%Y')}")

        trips = storage.load_trips(user_id)
        trip = next((t for t in trips if t["id"] == trip_id), None)
        await _send_edit_cities_msg(query.message, context, trip)
        return EDIT_CITIES

    return EDIT_CITY_TO


async def edit_city_to_text(update: Update, context) -> int:
    """Handle manual text date input for edit dateTo."""
    logger.warning("edit_city_to_text received text: %r", update.message.text)
    ds = parse_date(update.message.text)
    if not ds:
        await update.message.reply_text("❌ Неверный формат даты. Попробуйте ДД.ММ.ГГГГ:")
        return EDIT_CITY_TO

    user_id = update.effective_user.id
    trip_id = context.user_data["edit_trip_id"]
    idx = context.user_data["edit_city_idx"]

    trips = storage.load_trips(user_id)
    trip = next((t for t in trips if t["id"] == trip_id), None)
    if not trip or idx >= len(trip["cities"]):
        await update.message.reply_text("Поездка не найдена.", reply_markup=main_keyboard())
        return ConversationHandler.END

    trip["cities"][idx]["dateFrom"] = context.user_data["edit_new_from"]
    trip["cities"][idx]["dateTo"] = ds
    storage.update_trip(user_id, trip_id, {"cities": trip["cities"]})

    trips = storage.load_trips(user_id)
    trip = next((t for t in trips if t["id"] == trip_id), None)
    await _send_edit_cities_msg(update.message, context, trip)
    return EDIT_CITIES


async def edit_add_pick(update: Update, context) -> int:
    """Handle city selection when adding a city during edit."""
    query = update.callback_query
    await query.answer()
    city_name = query.data.split(":", 1)[1]

    if city_name == "__custom__":
        await query.edit_message_text("🏙 Введите название города:")
        return EDIT_ADD_NAME

    context.user_data["edit_new_city"] = {"name": city_name}
    await query.edit_message_text(f"🏙 Город: {city_name}")
    today = date.today()
    kb = _eafrom_picker.build(today.year, today.month)
    await query.message.reply_text("📅 Дата заезда:", reply_markup=kb)
    return EDIT_ADD_FROM


async def edit_add_name(update: Update, context) -> int:
    """Handle custom city name input during edit-add."""
    context.user_data["edit_new_city"] = {"name": update.message.text.strip()}
    today = date.today()
    kb = _eafrom_picker.build(today.year, today.month)
    await update.message.reply_text("📅 Дата заезда:", reply_markup=kb)
    return EDIT_ADD_FROM


async def edit_add_cal_from(update: Update, context) -> int:
    """Handle calendar for add-city dateFrom."""
    query = update.callback_query
    await query.answer()
    result = _eafrom_picker.parse(query.data)

    if result[0] == "noop":
        return EDIT_ADD_FROM

    if result[0] == "navigate":
        _, year, month = result
        kb = _eafrom_picker.build(year, month)
        await query.edit_message_reply_markup(reply_markup=kb)
        return EDIT_ADD_FROM

    if result[0] == "day":
        _, year, month, day = result
        ds = f"{year}-{month:02d}-{day:02d}"
        context.user_data["edit_new_city"]["dateFrom"] = ds
        d = date(year, month, day)
        await query.edit_message_text(f"📅 Заезд: {d.strftime('%d.%m.%Y')}")
        today = date.today()
        kb = _eato_picker.build(today.year, today.month)
        await query.message.reply_text("📅 Дата выезда:", reply_markup=kb)
        return EDIT_ADD_TO

    return EDIT_ADD_FROM


async def edit_add_from_text(update: Update, context) -> int:
    """Handle manual text date for add-city dateFrom."""
    logger.warning("edit_add_from_text received text: %r", update.message.text)
    ds = parse_date(update.message.text)
    if not ds:
        await update.message.reply_text("❌ Неверный формат даты. Попробуйте ДД.ММ.ГГГГ:")
        return EDIT_ADD_FROM
    context.user_data["edit_new_city"]["dateFrom"] = ds
    today = date.today()
    kb = _eato_picker.build(today.year, today.month)
    await update.message.reply_text("📅 Дата выезда:", reply_markup=kb)
    return EDIT_ADD_TO


async def edit_add_cal_to(update: Update, context) -> int:
    """Handle calendar for add-city dateTo."""
    query = update.callback_query
    await query.answer()
    result = _eato_picker.parse(query.data)

    if result[0] == "noop":
        return EDIT_ADD_TO

    if result[0] == "navigate":
        _, year, month = result
        kb = _eato_picker.build(year, month)
        await query.edit_message_reply_markup(reply_markup=kb)
        return EDIT_ADD_TO

    if result[0] == "day":
        _, year, month, day = result
        ds = f"{year}-{month:02d}-{day:02d}"
        context.user_data["edit_new_city"]["dateTo"] = ds

        user_id = update.effective_user.id
        trip_id = context.user_data["edit_trip_id"]
        trips = storage.load_trips(user_id)
        trip = next((t for t in trips if t["id"] == trip_id), None)
        if not trip:
            await query.edit_message_text("Поездка не найдена.")
            return ConversationHandler.END

        trip["cities"].append(context.user_data["edit_new_city"])
        storage.update_trip(user_id, trip_id, {"cities": trip["cities"]})

        d = date(year, month, day)
        await query.edit_message_text(f"📅 Выезд: {d.strftime('%d.%m.%Y')}")

        trips = storage.load_trips(user_id)
        trip = next((t for t in trips if t["id"] == trip_id), None)
        context.user_data.pop("edit_new_city", None)
        await _send_edit_field_choices_msg(query.message, trip)
        return EDIT_CITIES

    return EDIT_ADD_TO


async def edit_add_to_text(update: Update, context) -> int:
    """Handle manual text date for add-city dateTo."""
    logger.warning("edit_add_to_text received text: %r", update.message.text)
    ds = parse_date(update.message.text)
    if not ds:
        await update.message.reply_text("❌ Неверный формат даты. Попробуйте ДД.ММ.ГГГГ:")
        return EDIT_ADD_TO

    user_id = update.effective_user.id
    trip_id = context.user_data["edit_trip_id"]
    trips = storage.load_trips(user_id)
    trip = next((t for t in trips if t["id"] == trip_id), None)
    if not trip:
        await update.message.reply_text("Поездка не найдена.", reply_markup=main_keyboard())
        return ConversationHandler.END

    context.user_data["edit_new_city"]["dateTo"] = ds
    trip["cities"].append(context.user_data["edit_new_city"])
    storage.update_trip(user_id, trip_id, {"cities": trip["cities"]})

    trips = storage.load_trips(user_id)
    trip = next((t for t in trips if t["id"] == trip_id), None)
    context.user_data.pop("edit_new_city", None)
    await _send_edit_field_choices_msg(update.message, trip)
    return EDIT_CITIES


async def edit_cancel(update: Update, context) -> int:
    """Cancel edit conversation."""
    context.user_data.pop("edit_trip_id", None)
    context.user_data.pop("edit_city_idx", None)
    context.user_data.pop("edit_new_from", None)
    context.user_data.pop("edit_new_city", None)
    context.user_data.pop("_editing_city_name", None)
    await update.message.reply_text("❌ Редактирование отменено.", reply_markup=main_keyboard())
    return ConversationHandler.END


# ── Delete Trip ──────────────────────────────────────────────────────────

async def cmd_delete(update: Update, context) -> None:
    user_id = update.effective_user.id
    trips = storage.load_trips(user_id)
    if not trips:
        await update.message.reply_text(
            "У вас нет поездок.",
            reply_markup=main_keyboard(),
        )
        return

    await update.message.reply_text("🗑 Удаление", reply_markup=cancel_keyboard())
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

    trips = storage.load_trips(user_id)
    trip = next((t for t in trips if t["id"] == trip_id), None)
    if not trip:
        await query.edit_message_text("Поездка не найдена.")
        return

    context.user_data["del_trip_id"] = trip_id
    await query.edit_message_text(
        f"🗑 Удалить <b>{_html(trip['name'])}</b>?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Да, удалить", callback_data="delconfirm:yes"),
            InlineKeyboardButton("❌ Нет", callback_data="delconfirm:no"),
        ]]),
    )


async def delete_confirm_callback(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":")[1]

    if choice == "yes":
        trip_id = context.user_data.pop("del_trip_id", None)
        user_id = update.effective_user.id
        if trip_id and storage.delete_trip(user_id, trip_id):
            await query.edit_message_text("🗑 Поездка удалена.")
        else:
            await query.edit_message_text("Поездка не найдена.")
    else:
        context.user_data.pop("del_trip_id", None)
        await query.edit_message_text("↩️ Отменено.")


# ── Standalone cancel (outside conversations) ────────────────────────────

async def cancel_standalone(update: Update, context) -> None:
    """Handle Cancel button press outside of any conversation."""
    await update.message.reply_text("↩️ Отменено.", reply_markup=main_keyboard())


# ── Reminders ─────────────────────────────────────────────────────────────

MSK = timezone(timedelta(hours=3))
REMIND_TIME = dt_time(hour=22, minute=0, tzinfo=MSK)  # 22:00 MSK
REMIND_DAYS = (7, 1)  # за неделю и за день
TEST_REMIND_DELAY = 60  # секунд после создания поездки (тест)


async def _send_creation_reminder(context) -> None:
    """One-shot job: send a test push 1 min after trip creation."""
    data = context.job.data
    user_id = data["user_id"]
    trip = data["trip"]
    emoji = EMOJI.get(trip["type"], "")
    name = _html(trip["name"])
    route = " → ".join(_html(c["name"]) for c in trip.get("cities", []))
    text = f"🔔 Напоминание: {emoji} <b>{name}</b>\n📍 {route}"
    try:
        await context.bot.send_message(user_id, text, parse_mode="HTML")
        logger.info("Sent creation reminder to %d: %s", user_id, trip["name"])
    except Exception as e:
        logger.warning("Failed creation reminder to %d: %s", user_id, e)


def schedule_creation_reminder(app, user_id: int, trip: dict) -> None:
    """Schedule a test reminder 1 min after trip creation."""
    app.job_queue.run_once(
        _send_creation_reminder,
        when=TEST_REMIND_DELAY,
        data={"user_id": user_id, "trip": trip},
        name=f"creation_remind_{user_id}_{trip['id']}",
    )
    logger.info("Scheduled creation reminder for user %d, trip %s in %ds",
                user_id, trip["id"], TEST_REMIND_DELAY)


async def send_reminders(context) -> None:
    """Daily job: check all users' trips and send reminders."""
    bot = context.bot
    # Use Moscow date, not server date
    today = datetime.now(MSK).date()
    user_ids = storage.all_user_ids()
    logger.info("Reminder check: %s, users: %d", today, len(user_ids))

    for user_id in user_ids:
        trips = storage.load_trips(user_id)
        for tr in trips:
            cities = tr.get("cities", [])
            if not cities:
                continue
            try:
                first = datetime.strptime(cities[0]["dateFrom"], "%Y-%m-%d").date()
            except (ValueError, KeyError):
                continue

            diff = (first - today).days
            if diff not in REMIND_DAYS:
                continue

            emoji = EMOJI.get(tr["type"], "")
            name = _html(tr["name"])
            route = " → ".join(_html(c["name"]) for c in cities)

            if diff == 7:
                text = f"🔔 Через неделю: {emoji} <b>{name}</b>\n📍 {route}"
            else:
                text = f"🔔 Завтра: {emoji} <b>{name}</b>\n📍 {route}"

            try:
                await bot.send_message(user_id, text, parse_mode="HTML")
                logger.info("Sent reminder to %d: %s (%d days)", user_id, tr["name"], diff)
            except Exception as e:
                logger.warning("Failed to send reminder to user %d: %s", user_id, e)


async def cmd_test_remind(update: Update, context) -> None:
    """Manually trigger reminder check for the calling user."""
    await update.message.reply_text("🔄 Проверяю напоминания...")
    today = datetime.now(MSK).date()
    user_id = update.effective_user.id
    trips = storage.load_trips(user_id)
    sent = 0
    for tr in trips:
        cities = tr.get("cities", [])
        if not cities:
            continue
        try:
            first = datetime.strptime(cities[0]["dateFrom"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        diff = (first - today).days
        emoji = EMOJI.get(tr["type"], "")
        name = _html(tr["name"])
        route = " → ".join(_html(c["name"]) for c in cities)
        await update.message.reply_text(
            f"  {emoji} {name}: через <b>{diff}</b> дн. (remind: {', '.join(str(d) for d in REMIND_DAYS)})",
            parse_mode="HTML",
        )
        if diff in REMIND_DAYS:
            if diff == 7:
                text = f"🔔 Через неделю: {emoji} <b>{name}</b>\n📍 {route}"
            else:
                text = f"🔔 Завтра: {emoji} <b>{name}</b>\n📍 {route}"
            await update.message.reply_text(text, parse_mode="HTML")
            sent += 1
    await update.message.reply_text(
        f"✅ Готово. Поездок: {len(trips)}, напоминаний: {sent}",
        reply_markup=main_keyboard(),
    )


# ── Voice message handler ─────────────────────────────────────────────────

VOICE_FREE_LIMIT = 5
VOICE_MAX_DURATION = 60  # seconds


async def handle_voice(update: Update, context) -> None:
    """Handle voice message: transcribe via Whisper, parse trip via GPT."""
    msg = update.message
    uid = msg.from_user.id

    # Check duration
    if msg.voice.duration > VOICE_MAX_DURATION:
        await msg.reply_text(
            f"⚠️ Голосовое сообщение слишком длинное (макс. {VOICE_MAX_DURATION} сек).",
            reply_markup=main_keyboard(),
        )
        return

    # Check free limit
    if not storage.is_premium(uid) and storage.get_voice_count(uid) >= VOICE_FREE_LIMIT:
        await msg.reply_text(
            f"🔒 Бесплатный лимит ({VOICE_FREE_LIMIT} голосовых) исчерпан.\n\n"
            "Для безлимитного доступа к голосовому вводу — "
            "свяжитесь с @goshaginyan.",
            reply_markup=main_keyboard(),
        )
        return

    await msg.reply_text("🎙 Распознаю голосовое...")

    try:
        voice_file = await msg.voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()

        text = await voice.transcribe(bytes(voice_bytes))
        if not text:
            await msg.reply_text(
                "⚠️ Не удалось распознать голосовое сообщение.",
                reply_markup=main_keyboard(),
            )
            return

        await msg.reply_text(f"📝 <i>{_html(text)}</i>", parse_mode="HTML")

        data = await voice.parse_trip(text)
        if not data:
            await msg.reply_text(
                "⚠️ Не удалось извлечь данные о поездке.\nПопробуйте ещё раз, например:\n"
                "<i>«Еду в Париж с 20 по 25 апреля, потом в Лион до 28-го»</i>",
                parse_mode="HTML",
                reply_markup=main_keyboard(),
            )
            return

        cities = data.get("cities", [])
        if not cities:
            await msg.reply_text(
                "⚠️ Не удалось определить города и даты.\nПопробуйте указать конкретнее.",
                reply_markup=main_keyboard(),
            )
            return

        trip = storage.add_trip(
            user_id=uid,
            name=data.get("name", "Поездка"),
            trip_type=data.get("type", "trip"),
            cities=cities,
        )

        storage.increment_voice_count(uid)
        schedule_creation_reminder(context.application, uid, trip)

        remaining = VOICE_FREE_LIMIT - storage.get_voice_count(uid)
        emoji = EMOJI.get(trip["type"], "")
        name = _html(trip["name"])
        route = " → ".join(
            f'{_html(c["name"])} ({c["dateFrom"]} — {c["dateTo"]})' for c in trip["cities"]
        )
        text = f"✅ Поездка создана!\n\n{emoji} <b>{name}</b>\n📍 {route}"
        if not storage.is_premium(uid) and remaining >= 0:
            text += f"\n\n🎙 Осталось голосовых: {remaining}/{VOICE_FREE_LIMIT}"
        await msg.reply_text(text, parse_mode="HTML", reply_markup=main_keyboard())
    except Exception:
        logger.exception("Voice handler error")
        await msg.reply_text(
            "⚠️ Ошибка при обработке голосового сообщения.",
            reply_markup=main_keyboard(),
        )


# ── Post-init: set commands & menu button ────────────────────────────────

async def post_init(application) -> None:
    """Set bot commands and menu button after startup."""
    commands = [
        BotCommand("new", "Новая поездка"),
        BotCommand("list", "Все поездки"),
        BotCommand("edit", "Редактировать"),
        BotCommand("delete", "Удалить"),
        BotCommand("help", "Справка"),
    ]
    await application.bot.set_my_commands(commands)
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    logger.info("Bot commands and menu button configured.")


# ── Build bot application ────────────────────────────────────────────────

def _build_bot_app(token: str) -> Application:
    app = ApplicationBuilder().token(token).post_init(post_init).build()

    # Filter for all menu buttons (used to exclude from text handlers)
    menu_btn_filter = filters.Text([BTN_CANCEL, BTN_LIST, BTN_EDIT, BTN_DELETE, BTN_HELP, BTN_NEW])

    # Conversation for creating new trip (TYPE → NAME → CITY → DATES)
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("new", new_start),
            MessageHandler(filters.Text([BTN_NEW]), new_start),
        ],
        states={
            TYPE: [CallbackQueryHandler(new_type, pattern=r"^type:")],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_btn_filter, new_name)],
            CITY_PICK: [
                CallbackQueryHandler(new_city_pick, pattern=r"^city:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_btn_filter, new_city_name),
            ],
            CITY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_btn_filter, new_city_name)],
            CITY_FROM: [
                CallbackQueryHandler(cal_from_callback, pattern=r"^from:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_btn_filter, new_city_from),
            ],
            CITY_TO: [
                CallbackQueryHandler(cal_to_callback, pattern=r"^to:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_btn_filter, new_city_to),
            ],
            MORE_CITIES: [CallbackQueryHandler(new_more_cities, pattern=r"^more:")],
        },
        fallbacks=[
            CommandHandler("start", fallback_start),
            CommandHandler("help", fallback_help),
            CommandHandler("list", fallback_list),
            CommandHandler("trips", fallback_list),
            CommandHandler("edit", fallback_edit),
            CommandHandler("delete", fallback_delete),
            CommandHandler("cancel", new_cancel),
            MessageHandler(filters.Text([BTN_CANCEL]), new_cancel),
            MessageHandler(filters.Text([BTN_LIST]), fallback_list),
            MessageHandler(filters.Text([BTN_EDIT]), fallback_edit),
            MessageHandler(filters.Text([BTN_DELETE]), fallback_delete),
            MessageHandler(filters.Text([BTN_HELP]), fallback_help),
        ],
        per_message=False,
    )

    app.add_handler(conv_handler)

    # Conversation for editing trips
    edit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_start, pattern=r"^edit:"),
        ],
        states={
            EDIT_CITIES: [
                CallbackQueryHandler(edit_city_pick, pattern=r"^ecity:"),
            ],
            EDIT_ACTION: [
                CallbackQueryHandler(edit_action, pattern=r"^eact:"),
            ],
            EDIT_CITY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_btn_filter, edit_city_name),
            ],
            EDIT_CITY_FROM: [
                CallbackQueryHandler(edit_cal_from, pattern=r"^efrom:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_btn_filter, edit_city_from_text),
            ],
            EDIT_CITY_TO: [
                CallbackQueryHandler(edit_cal_to, pattern=r"^eto:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_btn_filter, edit_city_to_text),
            ],
            EDIT_ADD_PICK: [
                CallbackQueryHandler(edit_add_pick, pattern=r"^eacity:"),
            ],
            EDIT_ADD_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_btn_filter, edit_add_name),
            ],
            EDIT_ADD_FROM: [
                CallbackQueryHandler(edit_add_cal_from, pattern=r"^eafrom:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_btn_filter, edit_add_from_text),
            ],
            EDIT_ADD_TO: [
                CallbackQueryHandler(edit_add_cal_to, pattern=r"^eato:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_btn_filter, edit_add_to_text),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", edit_cancel),
            MessageHandler(filters.Text([BTN_CANCEL]), edit_cancel),
            CommandHandler("start", fallback_start),
            CommandHandler("help", fallback_help),
            CommandHandler("list", fallback_list),
            CommandHandler("trips", fallback_list),
            CommandHandler("edit", fallback_edit),
            CommandHandler("delete", fallback_delete),
            MessageHandler(filters.Text([BTN_NEW]), fallback_start),
            MessageHandler(filters.Text([BTN_LIST]), fallback_list),
            MessageHandler(filters.Text([BTN_EDIT]), fallback_edit),
            MessageHandler(filters.Text([BTN_DELETE]), fallback_delete),
            MessageHandler(filters.Text([BTN_HELP]), fallback_help),
        ],
        per_message=False,
    )
    app.add_handler(edit_conv)

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("trips", cmd_list))  # backward compat alias
    app.add_handler(CommandHandler("edit", cmd_edit))
    app.add_handler(CommandHandler("delete", cmd_delete))

    # Handle reply keyboard button presses
    app.add_handler(MessageHandler(filters.Text([BTN_LIST]), cmd_list))
    app.add_handler(MessageHandler(filters.Text([BTN_EDIT]), cmd_edit))
    app.add_handler(MessageHandler(filters.Text([BTN_DELETE]), cmd_delete))
    app.add_handler(MessageHandler(filters.Text([BTN_HELP]), cmd_help))

    # Standalone cancel (outside conversations)
    app.add_handler(MessageHandler(filters.Text([BTN_CANCEL]), cancel_standalone))
    app.add_handler(CommandHandler("cancel", cancel_standalone))

    # Test reminder command
    app.add_handler(CommandHandler("test_remind", cmd_test_remind))

    # Inline callbacks for delete with confirmation
    app.add_handler(CallbackQueryHandler(delete_callback, pattern=r"^del:"))
    app.add_handler(CallbackQueryHandler(delete_confirm_callback, pattern=r"^delconfirm:"))

    # Voice messages
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    return app


# ── Main ─────────────────────────────────────────────────────────────────

async def run() -> None:
    if not BOT_TOKEN:
        raise SystemExit("TRIPPA_BOT_TOKEN is not set")

    web_port = int(os.environ.get("PORT", os.environ.get("WEB_PORT", "8080")))

    bot_app = _build_bot_app(BOT_TOKEN)

    web_app = create_app(BOT_TOKEN, bot_app)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", web_port)

    async with bot_app:
        await bot_app.start()
        await site.start()
        logger.info("Trippa bot is running...")
        logger.info("Web API listening on port %d", web_port)

        # Schedule daily reminders at 22:00 MSK (19:00 UTC)
        bot_app.job_queue.run_daily(send_reminders, time=REMIND_TIME)
        logger.info("Reminders scheduled daily at %s", REMIND_TIME)

        await bot_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await bot_app.updater.stop()
            await bot_app.stop()
            await runner.cleanup()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
