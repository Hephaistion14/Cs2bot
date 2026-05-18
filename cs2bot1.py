import logging
import asyncio
import aiohttp
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# ============================================================
# ВСТАВЬ СВОЙ ТОКЕН СЮДА
TOKEN = "YOUR_BOT_TOKEN"
ALERTS_FILE = "alerts.json"
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STEP_TOURNAMENT = 0
STEP_WEAPON = 1
STEP_QUALITY = 2
STEP_WEAR = 3
STEP_CHARM = 4
STEP_PRICE = 5
STEP_YEAR = 6

ALERT_QUERY = 10
ALERT_PRICE = 11
ALERT_INTERVAL = 12

WEAPONS = [
    "Любое", "AK-47", "M4A4", "M4A1-S", "AWP", "Desert Eagle",
    "USP-S", "Glock-18", "MP9", "MAC-10", "P250", "Five-SeveN",
    "Butterfly Knife", "Karambit", "Bayonet", "Flip Knife"
]
QUALITIES = ["Любое", "Covert", "Classified", "Restricted", "Mil-Spec", "Industrial Grade"]
WEAR_OPTIONS = [
    "Любой", "Factory New (FN)", "Minimal Wear (MW)",
    "Field-Tested (FT)", "Well-Worn (WW)", "Battle-Scarred (BS)"
]
WEAR_MAP = {
    "Factory New (FN)": "Factory New",
    "Minimal Wear (MW)": "Minimal Wear",
    "Field-Tested (FT)": "Field-Tested",
    "Well-Worn (WW)": "Well-Worn",
    "Battle-Scarred (BS)": "Battle-Scarred",
}
PRICE_RANGES = ["Любой", "0-10$", "10-50$", "50-200$", "200-500$", "500$+"]
PRICE_MAP = {
    "0-10$": (0, 10),
    "10-50$": (10, 50),
    "50-200$": (50, 200),
    "200-500$": (200, 500),
    "500$+": (500, 999999),
}
STICKER_YEARS = [
    "Любой", "до 2016", "до 2017", "до 2018", "до 2019",
    "до 2020", "до 2021", "до 2022", "до 2023", "до 2024"
]
POPULAR_TOURNAMENTS = [
    "PGL Antwerp 2022", "IEM Rio 2022",
    "BLAST Paris 2023", "IEM Katowice 2024",
    "PGL Copenhagen 2024", "Stockholm 2021",
    "Berlin 2019", "Katowice 2019"
]
CHECK_INTERVALS = ["5 минут", "15 минут", "30 минут", "1 час", "3 часа"]
INTERVAL_SECONDS = {
    "5 минут": 300, "15 минут": 900, "30 минут": 1800,
    "1 час": 3600, "3 часа": 10800,
}


def load_alerts():
    if os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_alerts(data):
    with open(ALERTS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


alerts_store = load_alerts()


def make_keyboard(options, columns=2):
    buttons = [InlineKeyboardButton(opt, callback_data=opt) for opt in options]
    rows = []
    for i in range(0, len(buttons), columns):
        rows.append(buttons[i:i + columns])
    return rows


def item_matches_year(name, max_year):
    if max_year == 9999:
        return True
    name_lower = name.lower()
    for year in range(2013, 2026):
        if str(year) in name_lower and year > max_year:
            return False
    return True


# ── Команды ──────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "CS2 Skin Finder\n\n"
        "Ищу скины с турнирными наклейками:\n"
        "Steam, CSFloat, Skinport\n\n"
        "/find - поиск с фильтрами\n"
        "/alert - уведомление о цене\n"
        "/myalerts - мои уведомления\n"
        "/help - справка"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Справка:\n\n"
        "/find - поиск с фильтрами\n"
        "/alert - следить за ценой\n"
        "/myalerts - активные уведомления\n"
        "/stopalerts - отключить все\n"
        "/cancel - отменить действие"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Отменено. /find - поиск")
    return ConversationHandler.END


# ── Поиск ────────────────────────────────────────────────────

async def find_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    rows = make_keyboard(POPULAR_TOURNAMENTS, columns=2)
    rows.append([InlineKeyboardButton("Ввести вручную", callback_data="__manual__")])
    await update.message.reply_text(
        "Шаг 1/7 - Турнир или наклейка\n\nВыбери или введи вручную:",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_TOURNAMENT


async def tournament_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "__manual__":
        await q.edit_message_text("Введи название турнира или наклейки:")
        return STEP_TOURNAMENT
    context.user_data["tournament"] = q.data
    rows = make_keyboard(WEAPONS, columns=3)
    await q.edit_message_text(
        "Выбрано: " + q.data + "\n\nШаг 2/7 - Оружие",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_WEAPON


async def tournament_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tournament"] = update.message.text.strip()
    rows = make_keyboard(WEAPONS, columns=3)
    await update.message.reply_text(
        "Выбрано: " + update.message.text.strip() + "\n\nШаг 2/7 - Оружие",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_WEAPON


async def weapon_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["weapon"] = q.data
    rows = make_keyboard(QUALITIES, columns=2)
    await q.edit_message_text(
        "Выбрано: " + q.data + "\n\nШаг 3/7 - Качество",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_QUALITY


async def quality_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["quality"] = q.data
    rows = make_keyboard(WEAR_OPTIONS, columns=2)
    await q.edit_message_text(
        "Выбрано: " + q.data + "\n\nШаг 4/7 - Износ",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_WEAR


async def wear_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["wear"] = q.data
    rows = make_keyboard(["Да - с брелком", "Нет - без брелка", "Любой"], columns=2)
    await q.edit_message_text(
        "Выбрано: " + q.data + "\n\nШаг 5/7 - Брелок",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_CHARM


async def charm_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["charm"] = q.data
    rows = make_keyboard(PRICE_RANGES, columns=3)
    await q.edit_message_text(
        "Выбрано: " + q.data + "\n\nШаг 6/7 - Цена",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_PRICE


async def price_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["price"] = q.data
    rows = make_keyboard(STICKER_YEARS, columns=3)
    await q.edit_message_text(
        "Выбрано: " + q.data + "\n\nШаг 7/7 - Год наклеек",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_YEAR


async def year_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["year"] = q.data
    d = context.user_data
    await q.edit_message_text(
        "Ищу:\n"
        "Турнир: " + d.get("tournament", "?") + "\n"
        "Оружие: " + d.get("weapon", "?") + "\n"
        "Износ: " + d.get("wear", "?") + "\n"
        "Цена: " + d.get("price", "?") + "\n"
        "Год: " + d.get("year", "?") + "\n\n"
        "Подожди..."
    )
    results = await do_search(d)
    await send_results(q.message.chat_id, results, context)
    return ConversationHandler.END


# ── Алерты ───────────────────────────────────────────────────

async def alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Новое уведомление\n\nВведи название скина или турнира:"
    )
    return ALERT_QUERY


async def alert_query_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["alert_query"] = update.message.text.strip()
    await update.message.reply_text(
        "Отслеживаю: " + context.user_data["alert_query"] + "\n\nВведи максимальную цену ($):"
    )
    return ALERT_PRICE


async def alert_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip().replace("$", "").replace(",", "."))
        context.user_data["alert_price"] = price
        rows = make_keyboard(CHECK_INTERVALS, columns=3)
        await update.message.reply_text(
            "Макс. цена: $" + str(round(price, 2)) + "\n\nКак часто проверять?",
            reply_markup=InlineKeyboardMarkup(rows)
        )
        return ALERT_INTERVAL
    except ValueError:
        await update.message.reply_text("Введи число, например: 150")
        return ALERT_PRICE


async def alert_interval_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = str(q.message.chat_id)
    label = q.data
    alert = {
        "query": context.user_data["alert_query"],
        "target_price": context.user_data["alert_price"],
        "interval": INTERVAL_SECONDS.get(label, 300),
        "interval_label": label,
        "last_check": 0,
        "active": True,
        "created": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    alerts_store.setdefault(chat_id, []).append(alert)
    save_alerts(alerts_store)
    await q.edit_message_text(
        "Уведомление создано!\n\n"
        "Запрос: " + alert["query"] + "\n"
        "Цена: до $" + str(round(alert["target_price"], 2)) + "\n"
        "Интервал: каждые " + label + "\n\n"
        "Напишу как только найду подходящий скин!\n\n"
        "/myalerts - все уведомления"
    )
    return ConversationHandler.END


async def my_alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    active = [a for a in alerts_store.get(chat_id, []) if a.get("active")]
    if not active:
        await update.message.reply_text("Нет активных уведомлений.\n\n/alert - создать")
        return
    text = "Уведомления (" + str(len(active)) + "):\n\n"
    for i, a in enumerate(active, 1):
        text += str(i) + ". " + a["query"] + "\n"
        text += "   до $" + str(round(a["target_price"], 2)) + " | каждые " + a["interval_label"] + "\n\n"
    rows = [[InlineKeyboardButton("Удалить все", callback_data="__delete_all__")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))


async def stop_alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alerts_store[str(update.effective_chat.id)] = []
    save_alerts(alerts_store)
    await update.message.reply_text("Все уведомления отключены.")


async def delete_all_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    alerts_store[str(q.message.chat_id)] = []
    save_alerts(alerts_store)
    await q.edit_message_text("Удалено.\n\n/alert - создать новое")


async def watch_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.clear()
    context.user_data["alert_query"] = q.data.replace("__watch__", "")
    await q.message.reply_text(
        "Слежу за: " + context.user_data["alert_query"] + "\n\nВведи максимальную цену ($):"
    )
    return ALERT_PRICE


# ── Фоновая проверка ─────────────────────────────────────────

async def check_alerts_job(app):
    while True:
        await asyncio.sleep(60)
        now = datetime.now().timestamp()
        for chat_id, user_alerts in list(alerts_store.items()):
            for alert in user_alerts:
                if not alert.get("active"):
                    continue
                if now - alert.get("last_check", 0) < alert.get("interval", 300):
                    continue
                alert["last_check"] = now
                save_alerts(alerts_store)
                try:
                    results = await do_search({
                        "tournament": alert["query"],
                        "weapon": "Любое", "wear": "Любой",
                        "charm": "Любой", "price": "Любой", "year": "Любой"
                    })
                    matches = [r for r in results if r.get("price_raw", 999999) <= alert["target_price"]]
                    if matches:
                        text = "Найден скин по твоей цене!\n\n"
                        text += "Запрос: " + alert["query"] + "\n"
                        text += "Лимит: $" + str(round(alert["target_price"], 2)) + "\n"
                        text += "Найдено: " + str(len(matches)) + " шт.\n\n"
                        buttons = []
                        for item in matches[:3]:
                            text += item["platform"] + " - " + item["price"] + "\n"
                            buttons.append([InlineKeyboardButton(
                                "Купить " + item["platform"] + " " + item["price"],
                                url=item["link"]
                            )])
                        await app.bot.send_message(
                            int(chat_id), text,
                            reply_markup=InlineKeyboardMarkup(buttons)
                        )
                except Exception as e:
                    logger.error("Alert error " + chat_id + ": " + str(e))


# ── Площадки ─────────────────────────────────────────────────

async def do_search(filters_data):
    tournament = filters_data.get("tournament", "")
    weapon = filters_data.get("weapon", "Любое")
    wear = filters_data.get("wear", "Любой")
    price_range = filters_data.get("price", "Любой")
    charm = filters_data.get("charm", "Любой")
    year_filter = filters_data.get("year", "Любой")

    parts = []
    if weapon and weapon != "Любое":
        parts.append(weapon)
    parts.append(tournament)
    wear_name = WEAR_MAP.get(wear, "")
    if wear_name:
        parts.append(wear_name)
    query = " ".join(parts)

    price_min, price_max = PRICE_MAP.get(price_range, (0, 999999)) if price_range != "Любой" else (0, 999999)
    max_year = int(year_filter.replace("до ", "")) if year_filter != "Любой" else 9999

    async with aiohttp.ClientSession() as session:
        all_r = await asyncio.gather(
            fetch_steam(session, query),
            fetch_csfloat(session, query),
            fetch_skinport(session, query),
            return_exceptions=True
        )

    results = [item for r in all_r if isinstance(r, list) for item in r]

    if price_range != "Любой":
        results = [r for r in results if price_min <= r.get("price_raw", 999999) <= price_max]
    if charm == "Да - с брелком":
        results = [r for r in results if r.get("has_charm")]
    elif charm == "Нет - без брелка":
        results = [r for r in results if not r.get("has_charm")]
    if max_year != 9999:
        results = [r for r in results if item_matches_year(r.get("name", ""), max_year)]

    results.sort(key=lambda x: x.get("price_raw", 0))
    return results[:30]


async def fetch_steam(session, query):
    try:
        url = (
            "https://steamcommunity.com/market/search/render/"
            "?query=" + aiohttp.helpers.quote(query) +
            "&appid=730&norender=1&count=10"
        )
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return [{
                "platform": "Steam",
                "name": i.get("name", ""),
                "price": i.get("sell_price_text", "N/A"),
                "price_raw": i.get("sell_price", 0) / 100,
                "link": "https://steamcommunity.com/market/listings/730/" + i.get("hash_name", ""),
                "quantity": i.get("sell_listings", "?"),
                "has_charm": False,
            } for i in (data.get("results") or [])]
    except Exception as e:
        logger.error("Steam: " + str(e))
        return []


async def fetch_csfloat(session, query):
    try:
        url = (
            "https://csfloat.com/api/v1/listings"
            "?limit=10&sort_by=lowest_price&market_hash_name=" + aiohttp.helpers.quote(query)
        )
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            results = []
            for i in (data.get("data") or []):
                price_raw = i.get("price", 0) / 100
                results.append({
                    "platform": "CSFloat",
                    "name": i.get("item", {}).get("market_hash_name", ""),
                    "price": "$" + str(round(price_raw, 2)),
                    "price_raw": price_raw,
                    "link": "https://csfloat.com/item/" + str(i.get("id", "")),
                    "wear": i.get("item", {}).get("wear_name", ""),
                    "float": str(round(i.get("item", {}).get("float_value", 0), 4)),
                    "quantity": 1,
                    "has_charm": bool(i.get("item", {}).get("keychains")),
                })
            return results
    except Exception as e:
        logger.error("CSFloat: " + str(e))
        return []


async def fetch_skinport(session, query):
    try:
        async with session.get(
            "https://api.skinport.com/v1/items?app_id=730&currency=USD",
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            q = query.lower()
            results = []
            for i in data:
                if q in i.get("market_hash_name", "").lower():
                    p = i.get("min_price") or 0
                    results.append({
                        "platform": "Skinport",
                        "name": i.get("market_hash_name", ""),
                        "price": "$" + str(round(p, 2)) if p else "N/A",
                        "price_raw": p,
                        "link": "https://skinport.com/market?search=" + i.get("market_hash_name", ""),
                        "quantity": i.get("quantity", "?"),
                        "has_charm": False,
                    })
            return results[:10]
    except Exception as e:
        logger.error("Skinport: " + str(e))
        return []


# ── Отправка результатов ──────────────────────────────────────

async def send_results(chat_id, results, context):
    if not results:
        await context.bot.send_message(
            chat_id,
            "Ничего не найдено.\n\n/find - новый поиск"
        )
        return
    await context.bot.send_message(
        chat_id,
        "Найдено " + str(len(results)) + " результатов:"
    )
    for item in results[:15]:
        wear_line = "\nИзнос: " + item["wear"] if item.get("wear") else ""
        float_line = " | Float: " + item.get("float", "") if item.get("float") else ""
        charm_line = " [брелок]" if item.get("has_charm") else ""
        text = (
            item["platform"] + charm_line + "\n" +
            item["name"] + wear_line + float_line + "\n" +
            "Цена: " + item["price"] + " | " + str(item.get("quantity", "?")) + " шт."
        )
        rows = [[
            InlineKeyboardButton("Купить", url=item["link"]),
            InlineKeyboardButton("Следить за ценой", callback_data="__watch__" + item["name"][:40])
        ]]
        await context.bot.send_message(
            chat_id, text,
            reply_markup=InlineKeyboardMarkup(rows)
        )
        await asyncio.sleep(0.3)
    await context.bot.send_message(
        chat_id,
        "/find - новый поиск | /alert - уведомление"
    )


# ── Main ─────────────────────────────────────────────────────

async def post_init(app):
    asyncio.create_task(check_alerts_job(app))


def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    search_conv = ConversationHandler(
        entry_points=[CommandHandler("find", find_cmd)],
        states={
            STEP_TOURNAMENT: [
                CallbackQueryHandler(tournament_chosen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, tournament_text),
            ],
            STEP_WEAPON: [CallbackQueryHandler(weapon_chosen)],
            STEP_QUALITY: [CallbackQueryHandler(quality_chosen)],
            STEP_WEAR: [CallbackQueryHandler(wear_chosen)],
            STEP_CHARM: [CallbackQueryHandler(charm_chosen)],
            STEP_PRICE: [CallbackQueryHandler(price_chosen)],
            STEP_YEAR: [CallbackQueryHandler(year_chosen)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=120,
        allow_reentry=True,
    )

    alert_conv = ConversationHandler(
        entry_points=[
            CommandHandler("alert", alert_cmd),
            CallbackQueryHandler(watch_cb, pattern="^__watch__"),
        ],
        states={
            ALERT_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, alert_query_received)],
            ALERT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, alert_price_received)],
            ALERT_INTERVAL: [CallbackQueryHandler(alert_interval_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=120,
        allow_reentry=True,
    )

    app.add_handler(search_conv)
    app.add_handler(alert_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("myalerts", my_alerts_cmd))
    app.add_handler(CommandHandler("stopalerts", stop_alerts_cmd))
    app.add_handler(CallbackQueryHandler(delete_all_cb, pattern="^__delete_all__$"))

    print("Bot started!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
