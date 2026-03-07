#!/usr/bin/env python3
"""Trippa Telegram Bot — manage travel plans from Telegram."""

import calendar
import logging
from datetime import datetime, date

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

POPULAR_CITIES = [
    "Москва", "Санкт-Петербург", "Стамбул", "Париж",
    "Рим", "Барселона", "Дубай", "Бангкок",
    "Тбилиси", "Ереван", "Бали", "Лондон",
]

MONTH_NAMES_RU = [
    "", "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
    "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек",
]

# ── Button labels (used for ReplyKeyboard and matching) ──────────────────
BTN_NEW = "➕ Новая поездка"
BTN_TRIPS = "📋 Мои поездки"
BTN_DELETE = "🗑 Удалить"
BTN_HELP = "❓ Помощь"
BTN_CANCEL = "❌ Отмена"

# Conversation states
NAME, TYPE, CITY_PICK, CITY_NAME, CITY_FROM, CITY_TO, MORE_CITIES = range(7)


# ── Keyboards ────────────────────────────────────────────────────────────

def main_keyboard() -> ReplyKeyboardMarkup:
    """Persistent main menu keyboard at the bottom of the chat."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_NEW), KeyboardButton(BTN_TRIPS)],
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


# ── Calendar helpers ─────────────────────────────────────────────────────

def build_month_keyboard(year: int, month: int, prefix: str) -> InlineKeyboardMarkup:
    """Build an inline calendar for a given month."""
    rows = []
    # Header: < Month Year >
    rows.append([
        InlineKeyboardButton("◀", callback_data=f"{prefix}:prev:{year}:{month}"),
        InlineKeyboardButton(f"{MONTH_NAMES_RU[month]} {year}", callback_data="noop"),
        InlineKeyboardButton("▶", callback_data=f"{prefix}:next:{year}:{month}"),
    ])
    # Weekday headers
    rows.append([
        InlineKeyboardButton(d, callback_data="noop")
        for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    ])
    # Day grid
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="noop"))
            else:
                row.append(InlineKeyboardButton(
                    str(day),
                    callback_data=f"{prefix}:day:{year}:{month}:{day}",
                ))
        rows.append(row)

    return InlineKeyboardMarkup(rows)


def shift_month(year: int, month: int, direction: int):
    """Shift month by +1 or -1, returning (year, month)."""
    month += direction
    if month > 12:
        month = 1
        year += 1
    elif month < 1:
        month = 12
        year -= 1
    return year, month


# ── Command Handlers ─────────────────────────────────────────────────────

async def cmd_start(update: Update, context) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"🌍 Привет, {_html(user.first_name)}!\n\n"
        "<b>Trippa</b> — бот для планирования поездок.\n\n"
        "Используй кнопки внизу или команды:\n"
        f"  {BTN_NEW} — создать поездку\n"
        f"  {BTN_TRIPS} — посмотреть поездки\n"
        f"  {BTN_DELETE} — удалить поездку\n"
        f"  {BTN_HELP} — справка",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


async def cmd_help(update: Update, context) -> None:
    await update.message.reply_text(
        "📖 <b>Как пользоваться Trippa Bot</b>\n\n"
        f"<b>{BTN_NEW}</b> или /new — создать поездку пошагово\n"
        f"<b>{BTN_TRIPS}</b> или /trips — показать все поездки\n"
        f"<b>{BTN_DELETE}</b> или /delete — удалить поездку\n\n"
        "При создании поездки:\n"
        "1. Введите название\n"
        "2. Выберите тип (отпуск, командировка...)\n"
        "3. Выберите город из списка или введите свой\n"
        "4. Выберите даты в календаре\n\n"
        f"Нажмите <b>{BTN_CANCEL}</b> чтобы отменить создание.",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


async def cmd_trips(update: Update, context) -> None:
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

    # Send each trip as a separate message with its own delete button
    if upcoming:
        await update.message.reply_text(
            "📋 <b>Предстоящие:</b>", parse_mode="HTML",
        )
        for tr in upcoming:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🗑 Удалить", callback_data=f"del:{tr['id']}"),
            ]])
            await update.message.reply_text(
                fmt_trip(tr), parse_mode="HTML", reply_markup=kb,
            )

    if archive:
        await update.message.reply_text(
            "📦 <b>Архив:</b>", parse_mode="HTML",
        )
        for tr in archive:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🗑 Удалить", callback_data=f"del:{tr['id']}"),
            ]])
            await update.message.reply_text(
                fmt_trip(tr), parse_mode="HTML", reply_markup=kb,
            )


# ── New Trip Conversation ────────────────────────────────────────────────

async def new_start(update: Update, context) -> int:
    context.user_data["new_trip"] = {"cities": []}
    await update.message.reply_text(
        "✏️ Введите название поездки:",
        reply_markup=cancel_keyboard(),
    )
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
    await _send_city_picker(query.message, context)
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
    await _send_calendar(query.message, context, "from", "📅 Дата заезда:")
    return CITY_FROM


async def new_city_name(update: Update, context) -> int:
    city = {"name": update.message.text.strip()}
    context.user_data["current_city"] = city
    await _send_calendar(update.message, context, "from", "📅 Дата заезда:")
    return CITY_FROM


async def _send_calendar(message, context, prefix: str, text: str) -> None:
    """Send calendar for date selection starting from current month."""
    today = date.today()
    kb = build_month_keyboard(today.year, today.month, prefix)
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
    parts = query.data.split(":")

    action = parts[1]
    if action == "noop":
        return CITY_FROM

    if action in ("prev", "next"):
        year, month = int(parts[2]), int(parts[3])
        year, month = shift_month(year, month, -1 if action == "prev" else 1)
        kb = build_month_keyboard(year, month, "from")
        await query.edit_message_reply_markup(reply_markup=kb)
        return CITY_FROM

    if action == "day":
        year, month, day = int(parts[2]), int(parts[3]), int(parts[4])
        ds = f"{year}-{month:02d}-{day:02d}"
        context.user_data["current_city"]["dateFrom"] = ds
        d = date(year, month, day)
        await query.edit_message_text(f"📅 Заезд: {d.strftime('%d.%m.%Y')}")
        await _send_calendar(query.message, context, "to", "📅 Дата выезда:")
        return CITY_TO

    return CITY_FROM


async def new_city_from(update: Update, context) -> int:
    """Handle manual text date input for dateFrom."""
    ds = parse_date(update.message.text)
    if not ds:
        await update.message.reply_text("❌ Неверный формат даты. Попробуйте ДД.ММ.ГГГГ:")
        return CITY_FROM
    context.user_data["current_city"]["dateFrom"] = ds
    await _send_calendar(update.message, context, "to", "📅 Дата выезда:")
    return CITY_TO


async def cal_to_callback(update: Update, context) -> int:
    """Handle calendar navigation and day selection for dateTo."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    action = parts[1]
    if action == "noop":
        return CITY_TO

    if action in ("prev", "next"):
        year, month = int(parts[2]), int(parts[3])
        year, month = shift_month(year, month, -1 if action == "prev" else 1)
        kb = build_month_keyboard(year, month, "to")
        await query.edit_message_reply_markup(reply_markup=kb)
        return CITY_TO

    if action == "day":
        year, month, day = int(parts[2]), int(parts[3]), int(parts[4])
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


async def fallback_trips(update: Update, context) -> int:
    """Handle /trips while inside the conversation — reset and show trips."""
    context.user_data.pop("new_trip", None)
    context.user_data.pop("current_city", None)
    await cmd_trips(update, context)
    return ConversationHandler.END


async def fallback_delete(update: Update, context) -> int:
    """Handle /delete while inside the conversation — reset and show delete."""
    context.user_data.pop("new_trip", None)
    context.user_data.pop("current_city", None)
    await cmd_delete(update, context)
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


# ── Post-init: set commands & menu button ────────────────────────────────

async def post_init(application) -> None:
    """Set bot commands and menu button after startup."""
    commands = [
        BotCommand("new", "Новая поездка"),
        BotCommand("trips", "Мои поездки"),
        BotCommand("delete", "Удалить поездку"),
        BotCommand("help", "Справка"),
    ]
    await application.bot.set_my_commands(commands)
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    logger.info("Bot commands and menu button configured.")


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        logger.error("TRIPPA_BOT_TOKEN environment variable is not set!")
        raise SystemExit(1)

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # Conversation for creating new trip
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("new", new_start),
            MessageHandler(filters.Text([BTN_NEW]), new_start),
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Text([BTN_CANCEL]), new_name)],
            TYPE: [CallbackQueryHandler(new_type, pattern=r"^type:")],
            CITY_PICK: [CallbackQueryHandler(new_city_pick, pattern=r"^city:")],
            CITY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Text([BTN_CANCEL]), new_city_name)],
            CITY_FROM: [
                CallbackQueryHandler(cal_from_callback, pattern=r"^from:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Text([BTN_CANCEL]), new_city_from),
            ],
            CITY_TO: [
                CallbackQueryHandler(cal_to_callback, pattern=r"^to:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Text([BTN_CANCEL]), new_city_to),
            ],
            MORE_CITIES: [CallbackQueryHandler(new_more_cities, pattern=r"^more:")],
        },
        fallbacks=[
            CommandHandler("start", fallback_start),
            CommandHandler("help", fallback_help),
            CommandHandler("trips", fallback_trips),
            CommandHandler("delete", fallback_delete),
            CommandHandler("cancel", new_cancel),
            MessageHandler(filters.Text([BTN_CANCEL]), new_cancel),
            MessageHandler(filters.Text([BTN_TRIPS]), fallback_trips),
            MessageHandler(filters.Text([BTN_DELETE]), fallback_delete),
            MessageHandler(filters.Text([BTN_HELP]), fallback_help),
        ],
        per_message=False,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("trips", cmd_trips))
    app.add_handler(CommandHandler("delete", cmd_delete))
    # Handle reply keyboard button presses
    app.add_handler(MessageHandler(filters.Text([BTN_TRIPS]), cmd_trips))
    app.add_handler(MessageHandler(filters.Text([BTN_DELETE]), cmd_delete))
    app.add_handler(MessageHandler(filters.Text([BTN_HELP]), cmd_help))
    app.add_handler(CallbackQueryHandler(delete_callback, pattern=r"^del:"))

    logger.info("Trippa bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
