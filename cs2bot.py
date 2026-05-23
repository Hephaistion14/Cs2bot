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
TOKEN = "8831794929:AAHd6RDLRy6VfWSbV_36ZBcnpsKJkOPSUD8"
ALERTS_FILE = "alerts.json"
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STEP_YEAR = 0
STEP_WEAPON = 1
STEP_QUALITY = 2
STEP_WEAR = 3
STEP_CHARM = 4
STEP_PRICE = 5
STEP_TOURNAMENT = 6

ALERT_QUERY = 10
ALERT_PRICE = 11
ALERT_INTERVAL = 12

TRACK_QUERY = 20
TRACK_PERCENT = 21

TRACKS_FILE = "tracks.json"

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
    "Любой", "2014", "2015", "2016", "2017", "2018",
    "2019", "2020", "2021", "2022", "2023", "2024"
]
POPULAR_TOURNAMENTS = [
    "Любой (все турниры)",
    "PGL Antwerp 2022", "IEM Rio 2022",
    "BLAST Paris 2023", "IEM Katowice 2024",
    "PGL Copenhagen 2024", "Stockholm 2021",
    "Berlin 2019", "Katowice 2019",
    "Ввести вручную"
]
CHECK_INTERVALS = ["5 минут", "15 минут", "30 минут", "1 час", "3 часа"]
INTERVAL_SECONDS = {
    "5 минут": 300, "15 минут": 900, "30 минут": 1800,
    "1 час": 3600, "3 часа": 10800,
}

# Турниры по годам для фильтрации наклеек
TOURNAMENT_YEARS = {
    "Katowice 2014": 2014, "Cologne 2014": 2014,
    "Katowice 2015": 2015, "Cluj-Napoca 2015": 2015, "Cologne 2015": 2015,
    "Columbus 2016": 2016, "Cologne 2016": 2016, "Cluj-Napoca 2016": 2016,
    "Atlanta 2017": 2017, "Krakow 2017": 2017,
    "Boston 2018": 2018, "London 2018": 2018,
    "Katowice 2019": 2019, "Berlin 2019": 2019,
    "Stockholm 2021": 2021,
    "Antwerp 2022": 2022, "Rio 2022": 2022,
    "Paris 2023": 2023,
    "Katowice 2024": 2024, "Copenhagen 2024": 2024, "Shanghai 2024": 2024,
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


def load_tracks():
    if os.path.exists(TRACKS_FILE):
        with open(TRACKS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_tracks(data):
    with open(TRACKS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


tracks_store = load_tracks()


def make_keyboard(options, columns=2):
    buttons = [InlineKeyboardButton(opt, callback_data=opt) for opt in options]
    rows = []
    for i in range(0, len(buttons), columns):
        rows.append(buttons[i:i + columns])
    return rows


def sticker_passes_year_filter(sticker_name, max_year):
    """Проверяет что наклейка не новее max_year"""
    if max_year == 9999:
        return True
    sticker_lower = sticker_name.lower()
    # Ищем год в названии наклейки
    for year in range(2013, 2026):
        if str(year) in sticker_lower:
            return year <= max_year
    # Если год не найден — пропускаем
    return True


def item_passes_sticker_filter(stickers, max_year):
    """Все наклейки на скине должны быть не новее max_year"""
    if max_year == 9999 or not stickers:
        return True
    for sticker in stickers:
        name = sticker.get("name", "") or sticker.get("market_hash_name", "")
        if not sticker_passes_year_filter(name, max_year):
            return False
    return True


def format_stickers(stickers):
    """Форматирует список наклеек для отображения"""
    if not stickers:
        return ""
    names = []
    for s in stickers:
        name = s.get("name", "") or s.get("market_hash_name", "")
        if name:
            names.append(name)
    return ", ".join(names) if names else ""


# ── Команды ──────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "CS2 Skin Finder\n\n"
        "Ищу скины с турнирными наклейками:\n"
        "- CSFloat (с точным фильтром по наклейкам)\n"
        "- Steam, Skinport\n\n"
        "/find - поиск с фильтрами\n"
        "/alert - уведомление о цене\n"
        "/track - следить за ценой на cs.money, lisskins, cs.market\n"
        "/myalerts - мои уведомления\n"
        "/mytracks - мои отслеживания\n"
        "/help - справка"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Справка:\n\n"
        "/find - поиск с фильтрами\n"
        "/alert - следить за ценой\n"
        "/myalerts - активные уведомления\n"
        "/stopalerts - отключить все\n"
        "/cancel - отменить действие\n\n"
        "Фильтр по году наклеек работает точно только на CSFloat.\n"
        "Steam и Skinport показываются без фильтра по наклейкам."
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Отменено. /find - поиск")
    return ConversationHandler.END


# ── Поиск ────────────────────────────────────────────────────

async def find_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    rows = make_keyboard(STICKER_YEARS, columns=4)
    await update.message.reply_text(
        "Шаг 1/7 - Год наклеек\n\nВыбери максимальный год наклеек или Любой:",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_YEAR


async def year_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["year"] = q.data
    rows = make_keyboard(WEAPONS, columns=3)
    await q.edit_message_text(
        "Год: " + q.data + "\n\nШаг 2/7 - Оружие",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_WEAPON


async def weapon_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["weapon"] = q.data
    rows = make_keyboard(QUALITIES, columns=2)
    await q.edit_message_text(
        "Оружие: " + q.data + "\n\nШаг 3/7 - Качество",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_QUALITY


async def quality_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["quality"] = q.data
    rows = make_keyboard(WEAR_OPTIONS, columns=2)
    await q.edit_message_text(
        "Качество: " + q.data + "\n\nШаг 4/7 - Износ",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_WEAR


async def wear_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["wear"] = q.data
    rows = make_keyboard(["Да - с брелком", "Нет - без брелка", "Любой"], columns=2)
    await q.edit_message_text(
        "Износ: " + q.data + "\n\nШаг 5/7 - Брелок",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_CHARM


async def charm_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["charm"] = q.data
    rows = make_keyboard(PRICE_RANGES, columns=3)
    await q.edit_message_text(
        "Брелок: " + q.data + "\n\nШаг 6/7 - Цена",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_PRICE


async def price_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["price"] = q.data
    rows = make_keyboard(POPULAR_TOURNAMENTS, columns=2)
    await q.edit_message_text(
        "Цена: " + q.data + "\n\nШаг 7/7 - Турнир (необязательно)\n\nВыбери конкретный турнир или Любой:",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return STEP_TOURNAMENT


async def tournament_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "Ввести вручную":
        await q.edit_message_text("Введи название турнира или наклейки:")
        return STEP_TOURNAMENT
    if q.data == "Любой (все турниры)":
        context.user_data["tournament"] = ""
    else:
        context.user_data["tournament"] = q.data
    await start_search(q.message, context, edit=True)
    return ConversationHandler.END


async def tournament_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tournament"] = update.message.text.strip()
    await start_search(update.message, context, edit=False)
    return ConversationHandler.END


async def start_search(message, context, edit=False):
    d = context.user_data
    tournament_line = d.get("tournament", "") or "Любой"
    summary = (
        "Ищу:\n"
        "Год наклеек: до " + d.get("year", "Любой") + "\n"
        "Турнир: " + tournament_line + "\n"
        "Оружие: " + d.get("weapon", "Любое") + "\n"
        "Износ: " + d.get("wear", "Любой") + "\n"
        "Цена: " + d.get("price", "Любой") + "\n\n"
        "Подожди, это может занять 10-20 секунд..."
    )
    if edit:
        await message.edit_text(summary)
    else:
        await message.reply_text(summary)
    results = await do_search(d)
    await send_results(message.chat_id, results, context)


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

    max_year = int(year_filter) if year_filter != "Любой" else 9999

    # Строим поисковый запрос
    parts = []
    if weapon and weapon != "Любое":
        parts.append(weapon)
    if tournament:
        parts.append(tournament)
    query = " ".join(parts) if parts else ""

    price_min, price_max = PRICE_MAP.get(price_range, (0, 999999)) if price_range != "Любой" else (0, 999999)

    async with aiohttp.ClientSession() as session:
        all_r = await asyncio.gather(
            fetch_csfloat_with_stickers(session, query, weapon, wear, price_min, price_max, max_year, charm),
            fetch_steam(session, query, weapon, wear),
            fetch_skinport(session, query, weapon),
            return_exceptions=True
        )

    csfloat_results = all_r[0] if isinstance(all_r[0], list) else []
    steam_results = all_r[1] if isinstance(all_r[1], list) else []
    skinport_results = all_r[2] if isinstance(all_r[2], list) else []

    # Применяем ценовой фильтр к Steam и Skinport
    if price_range != "Любой":
        steam_results = [r for r in steam_results if price_min <= r.get("price_raw", 999999) <= price_max]
        skinport_results = [r for r in skinport_results if price_min <= r.get("price_raw", 999999) <= price_max]

    # CSFloat уже отфильтрован по наклейкам
    # Steam и Skinport — без фильтра по наклейкам, помечаем
    for r in steam_results:
        r["note"] = "наклейки не проверены"
    for r in skinport_results:
        r["note"] = "наклейки не проверены"

    results = csfloat_results + steam_results + skinport_results
    results.sort(key=lambda x: x.get("price_raw", 0))
    return results[:30]


async def fetch_csfloat_with_stickers(session, query, weapon, wear, price_min, price_max, max_year, charm):
    """CSFloat с фильтрацией по наклейкам"""
    try:
        results = []
        page = 0
        found = 0

        # Ищем пока не найдём 10 подходящих или не просмотрим 5 страниц
        while found < 10 and page < 5:
            params = "?limit=20&sort_by=lowest_price&page=" + str(page)
            if weapon and weapon != "Любое":
                params += "&category=0"

            # Строим запрос
            search_query = query if query else weapon if weapon != "Любое" else "AK-47"
            url = "https://csfloat.com/api/v1/listings" + params + "&market_hash_name=" + aiohttp.helpers.quote(search_query)

            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    break
                data = await resp.json()
                items = data.get("data") or []
                if not items:
                    break

                for i in items:
                    item_data = i.get("item", {})
                    price_raw = i.get("price", 0) / 100

                    # Ценовой фильтр
                    if price_raw < price_min or price_raw > price_max:
                        continue

                    # Фильтр по износу
                    if wear and wear != "Любой":
                        wear_name = WEAR_MAP.get(wear, "")
                        item_wear = item_data.get("wear_name", "")
                        if wear_name and item_wear != wear_name:
                            continue

                    # Фильтр по брелку
                    has_charm = bool(item_data.get("keychains"))
                    if charm == "Да - с брелком" and not has_charm:
                        continue
                    if charm == "Нет - без брелка" and has_charm:
                        continue

                    # Получаем наклейки
                    stickers = item_data.get("stickers") or []

                    # Фильтр по году наклеек
                    if max_year != 9999:
                        if not stickers:
                            continue  # Без наклеек — пропускаем
                        if not item_passes_sticker_filter(stickers, max_year):
                            continue

                    sticker_text = format_stickers(stickers)
                    results.append({
                        "platform": "CSFloat",
                        "name": item_data.get("market_hash_name", ""),
                        "price": "$" + str(round(price_raw, 2)),
                        "price_raw": price_raw,
                        "link": "https://csfloat.com/item/" + str(i.get("id", "")),
                        "wear": item_data.get("wear_name", ""),
                        "float": str(round(item_data.get("float_value", 0), 4)),
                        "quantity": 1,
                        "has_charm": has_charm,
                        "stickers": sticker_text,
                    })
                    found += 1
                    if found >= 10:
                        break

                page += 1
                await asyncio.sleep(0.5)  # Не спамим запросами

        return results
    except Exception as e:
        logger.error("CSFloat stickers: " + str(e))
        return []


async def fetch_steam(session, query, weapon):
    try:
        search = query if query else (weapon if weapon != "Любое" else "AK-47 Sticker")
        url = (
            "https://steamcommunity.com/market/search/render/"
            "?query=" + aiohttp.helpers.quote(search) +
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
                "stickers": "",
            } for i in (data.get("results") or [])]
    except Exception as e:
        logger.error("Steam: " + str(e))
        return []


async def fetch_skinport(session, query, weapon):
    try:
        async with session.get(
            "https://api.skinport.com/v1/items?app_id=730&currency=USD",
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            search = (query if query else weapon if weapon != "Любое" else "").lower()
            if not search:
                return []
            results = []
            for i in data:
                if search in i.get("market_hash_name", "").lower():
                    p = i.get("min_price") or 0
                    results.append({
                        "platform": "Skinport",
                        "name": i.get("market_hash_name", ""),
                        "price": "$" + str(round(p, 2)) if p else "N/A",
                        "price_raw": p,
                        "link": "https://skinport.com/market?search=" + i.get("market_hash_name", ""),
                        "quantity": i.get("quantity", "?"),
                        "has_charm": False,
                        "stickers": "",
                    })
            return results[:10]
    except Exception as e:
        logger.error("Skinport: " + str(e))
        return []


async def send_results(chat_id, results, context):
    if not results:
        await context.bot.send_message(
            chat_id,
            "Ничего не найдено.\n\nПопробуй изменить фильтры или выбрать другой год.\n\n/find - новый поиск"
        )
        return

    csfloat = [r for r in results if r["platform"] == "CSFloat"]
    other = [r for r in results if r["platform"] != "CSFloat"]

    await context.bot.send_message(
        chat_id,
        "Найдено " + str(len(results)) + " результатов:\n"
        "CSFloat (с фильтром наклеек): " + str(len(csfloat)) + "\n"
        "Steam + Skinport (без фильтра): " + str(len(other))
    )

    for item in results[:15]:
        wear_line = "\nИзнос: " + item["wear"] if item.get("wear") else ""
        float_line = " | Float: " + item.get("float", "") if item.get("float") else ""
        charm_line = " [брелок]" if item.get("has_charm") else ""
        sticker_line = "\nНаклейки: " + item["stickers"] if item.get("stickers") else ""
        note_line = "\n! " + item["note"] if item.get("note") else ""

        text = (
            item["platform"] + charm_line + "\n" +
            item["name"] + wear_line + float_line + "\n" +
            "Цена: " + item["price"] + " | " + str(item.get("quantity", "?")) + " шт." +
            sticker_line + note_line
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

# ── Track команды ────────────────────────────────────────────

async def track_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Отслеживание цены на cs.money, lisskins, cs.market\n\n"
        "Введи точное название скина (как на Steam):\n"
        "Например: AK-47 | Redline (Field-Tested)"
    )
    return TRACK_QUERY


async def track_query_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["track_query"] = update.message.text.strip()
    await update.message.reply_text(
        "Скин: " + context.user_data["track_query"] + "\n\n"
        "На сколько процентов ниже текущей минимальной цены уведомить?\n"
        "Введи число, например: 5"
    )
    return TRACK_PERCENT


async def track_percent_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        percent = float(update.message.text.strip().replace("%", ""))
        if percent <= 0 or percent > 50:
            await update.message.reply_text("Введи число от 1 до 50")
            return TRACK_PERCENT

        chat_id = str(update.effective_chat.id)
        item_name = context.user_data["track_query"]

        await update.message.reply_text(
            "Ищу текущую цену на " + item_name + "...\nПодожди несколько секунд."
        )

        prices = await fetch_all_track_prices(item_name)

        if not prices:
            await update.message.reply_text(
                "Не удалось найти цену на этот предмет.\n"
                "Проверь название и попробуй снова.\n\n/track - попробовать снова"
            )
            return ConversationHandler.END

        min_price = min(p["price"] for p in prices)
        threshold = round(min_price * (1 - percent / 100), 2)

        track = {
            "query": item_name,
            "percent": percent,
            "base_price": min_price,
            "threshold": threshold,
            "last_check": datetime.now().timestamp(),
            "active": True,
            "created": datetime.now().strftime("%d.%m.%Y %H:%M"),
        }

        tracks_store.setdefault(chat_id, []).append(track)
        save_tracks(tracks_store)

        prices_text = ""
        for p in prices:
            prices_text += "\n" + p["platform"] + ": $" + str(round(p["price"], 2))

        await update.message.reply_text(
            "Отслеживание создано!\n\n"
            "Скин: " + item_name + "\n"
            "Текущий минимум: $" + str(round(min_price, 2)) + "\n"
            "Уведомлю если появится дешевле: $" + str(threshold) + " (-" + str(percent) + "%)\n\n"
            "Текущие цены:" + prices_text + "\n\n"
            "/mytracks - все отслеживания\n"
            "/stoptracks - отключить все"
        )
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("Введи число, например: 5")
        return TRACK_PERCENT


async def my_tracks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    active = [t for t in tracks_store.get(chat_id, []) if t.get("active")]
    if not active:
        await update.message.reply_text("Нет активных отслеживаний.\n\n/track - создать")
        return
    text = "Отслеживания (" + str(len(active)) + "):\n\n"
    for i, t in enumerate(active, 1):
        text += str(i) + ". " + t["query"] + "\n"
        text += "   Порог: $" + str(round(t["threshold"], 2)) + " (-" + str(t["percent"]) + "%)\n\n"
    rows = [[InlineKeyboardButton("Удалить все", callback_data="__delete_tracks__")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))


async def stop_tracks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tracks_store[str(update.effective_chat.id)] = []
    save_tracks(tracks_store)
    await update.message.reply_text("Все отслеживания отключены.")


async def delete_tracks_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tracks_store[str(q.message.chat_id)] = []
    save_tracks(tracks_store)
    await q.edit_message_text("Удалено.\n\n/track - создать новое")


# ── Парсинг cs.money, lisskins, cs.market ────────────────────

async def fetch_csmoney(session, item_name):
    try:
        url = "https://cs.money/api/sell/offers?limit=20&offset=0&appId=730&name=" + aiohttp.helpers.quote(item_name)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://cs.money/",
        }
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            items = data.get("items") or []
            results = []
            for item in items[:5]:
                price = item.get("pricing", {}).get("computed") or item.get("pricing", {}).get("default")
                if price:
                    results.append({
                        "platform": "cs.money",
                        "price": float(price),
                        "link": "https://cs.money/market/sell-skins/?name=" + aiohttp.helpers.quote(item_name),
                    })
            return results
    except Exception as e:
        logger.error("cs.money: " + str(e))
        return []


async def fetch_lisskins(session, item_name):
    try:
        url = "https://lisskins.com/api/market/search?query=" + aiohttp.helpers.quote(item_name) + "&game=csgo&limit=20"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            items = data.get("data") or data.get("items") or []
            results = []
            for item in items[:5]:
                price = item.get("price") or item.get("cost")
                if price:
                    results.append({
                        "platform": "lisskins",
                        "price": float(price),
                        "link": "https://lisskins.com/market/csgo?search=" + aiohttp.helpers.quote(item_name),
                    })
            return results
    except Exception as e:
        logger.error("lisskins: " + str(e))
        return []


async def fetch_csmarket(session, item_name):
    try:
        url = "https://market.csgo.com/api/v2/search-item-by-hash-name?key=&hash_name=" + aiohttp.helpers.quote(item_name)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            items = data.get("data") or []
            results = []
            for item in items[:5]:
                price = item.get("price")
                if price:
                    results.append({
                        "platform": "cs.market",
                        "price": float(price) / 100,
                        "link": "https://market.csgo.com/" + aiohttp.helpers.quote(item_name),
                    })
            return results
    except Exception as e:
        logger.error("cs.market: " + str(e))
        return []


async def fetch_all_track_prices(item_name):
    async with aiohttp.ClientSession() as session:
        all_r = await asyncio.gather(
            fetch_csmoney(session, item_name),
            fetch_lisskins(session, item_name),
            fetch_csmarket(session, item_name),
            return_exceptions=True
        )
    results = []
    for r in all_r:
        if isinstance(r, list):
            results.extend(r)
    results.sort(key=lambda x: x["price"])
    return results


# ── Фоновая проверка треков ───────────────────────────────────

async def check_tracks_job(app):
    while True:
        await asyncio.sleep(120)
        now = datetime.now().timestamp()
        for chat_id, user_tracks in list(tracks_store.items()):
            for track in user_tracks:
                if not track.get("active"):
                    continue
                if now - track.get("last_check", 0) < 300:
                    continue
                track["last_check"] = now
                save_tracks(tracks_store)
                try:
                    prices = await fetch_all_track_prices(track["query"])
                    if not prices:
                        continue
                    min_price = min(p["price"] for p in prices)
                    threshold = track["threshold"]

                    if min_price <= threshold:
                        best = [p for p in prices if p["price"] <= threshold]
                        text = (
                            "Найдена низкая цена!\n\n"
                            "Скин: " + track["query"] + "\n"
                            "Порог: $" + str(round(threshold, 2)) + " (-" + str(track["percent"]) + "%)\n"
                            "Найдена цена: $" + str(round(min_price, 2)) + "\n\n"
                            "Площадки:\n"
                        )
                        buttons = []
                        for p in best[:3]:
                            text += p["platform"] + ": $" + str(round(p["price"], 2)) + "\n"
                            buttons.append([InlineKeyboardButton(
                                "Купить на " + p["platform"] + " $" + str(round(p["price"], 2)),
                                url=p["link"]
                            )])
                        await app.bot.send_message(
                            int(chat_id), text,
                            reply_markup=InlineKeyboardMarkup(buttons)
                        )
                        # Обновляем базовую цену
                        track["base_price"] = min_price
                        track["threshold"] = round(min_price * (1 - track["percent"] / 100), 2)
                        save_tracks(tracks_store)
                except Exception as e:
                    logger.error("Track check error " + chat_id + ": " + str(e))


async def post_init(app):
    asyncio.create_task(check_alerts_job(app))
    asyncio.create_task(check_tracks_job(app))


def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    search_conv = ConversationHandler(
        entry_points=[CommandHandler("find", find_cmd)],
        states={
            STEP_YEAR: [CallbackQueryHandler(year_chosen)],
            STEP_WEAPON: [CallbackQueryHandler(weapon_chosen)],
            STEP_QUALITY: [CallbackQueryHandler(quality_chosen)],
            STEP_WEAR: [CallbackQueryHandler(wear_chosen)],
            STEP_CHARM: [CallbackQueryHandler(charm_chosen)],
            STEP_PRICE: [CallbackQueryHandler(price_chosen)],
            STEP_TOURNAMENT: [
                CallbackQueryHandler(tournament_chosen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, tournament_text),
            ],
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

    track_conv = ConversationHandler(
        entry_points=[CommandHandler("track", track_cmd)],
        states={
            TRACK_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, track_query_received)],
            TRACK_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, track_percent_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=120,
        allow_reentry=True,
    )

    app.add_handler(search_conv)
    app.add_handler(alert_conv)
    app.add_handler(track_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("myalerts", my_alerts_cmd))
    app.add_handler(CommandHandler("stopalerts", stop_alerts_cmd))
    app.add_handler(CommandHandler("mytracks", my_tracks_cmd))
    app.add_handler(CommandHandler("stoptracks", stop_tracks_cmd))
    app.add_handler(CallbackQueryHandler(delete_all_cb, pattern="^__delete_all__$"))
    app.add_handler(CallbackQueryHandler(delete_tracks_cb, pattern="^__delete_tracks__$"))

    print("Bot started!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
