import os
import time
import json
import requests
import xml.etree.ElementTree as ET
from html import unescape
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN")

last_update_id = 0
sent_news = set()           # dedup: titles of news already pushed
last_news_check = 0
last_morning_date = None
NEWS_INTERVAL = 1800        # push new news every 30 min
subscribed_chats = set()    # chats that opted in to auto-alerts

# ─── Portfolio (cost basis in rubles) ────────────────────────────────────────

PORTFOLIO = {
    "psb":       {"rub": 50000,  "label": "Вклад ПСБ (20%, 210д)", "group": "liquid"},
    "ofz_26246": {"rub": 25230,  "label": "ОФЗ 26246",             "group": "bonds"},
    "ofz_26252": {"rub": 10208,  "label": "ОФЗ 26252",             "group": "bonds"},
    "ofz_26218": {"rub": 34830,  "label": "ОФЗ 26218",             "group": "bonds"},
    "tmos":      {"rub": 24998,  "label": "TMOS",                   "group": "stocks"},
    "sber":      {"rub": 19856,  "label": "Сбер",                   "group": "stocks"},
    "mts":       {"rub": 8680,   "label": "МТС",                    "group": "stocks"},
    "moex_s":    {"rub": 9591,   "label": "Мосбиржа",               "group": "stocks"},
    "lqdt":      {"rub": 16607,  "label": "LQDT",                   "group": "liquid"},
}

BOND_YIELDS = {
    "ofz_26246": 0.120,
    "ofz_26252": 0.125,
    "ofz_26218": 0.085,
}

RSS_SOURCES = [
    ("Банк России",      "https://www.cbr.ru/rss/RssPress"),
    ("Банк России",      "https://www.cbr.ru/rss/eventrss"),
    ("Московская биржа", "https://www.moex.com/export/news.aspx?cat=101"),
    ("Московская биржа", "https://www.moex.com/export/news.aspx?cat=102"),
]

CATEGORY_IMPACT = {
    "rate":   "⚡ Высокое влияние — ОФЗ, LQDT и вклад",
    "bonds":  "⚡ Высокое влияние — ОФЗ 26246, 26252, 26218",
    "stocks": "📌 Среднее влияние — Сбер, МТС, Мосбиржа, TMOS",
    "market": "📌 Среднее влияние — TMOS и акции портфеля",
}

# ─── Helpers ─────────────────────────────────────────────────────────────────

def rub(x):
    return "{:,.0f} ₽".format(x).replace(",", " ")

def pct(value, total):
    if total == 0:
        return 0.0
    return round(value / total * 100, 1)

def portfolio_totals():
    groups = {"bonds": 0.0, "stocks": 0.0, "liquid": 0.0}
    for v in PORTFOLIO.values():
        groups[v["group"]] += v["rub"]
    total = sum(groups.values())
    return total, groups["bonds"], groups["stocks"], groups["liquid"]

def clean_text(text):
    if not text:
        return ""
    text = unescape(text)
    for ch in ["\n", "\r", "\t"]:
        text = text.replace(ch, " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()

# ─── MOEX ISS API ────────────────────────────────────────────────────────────

def fetch_moex_price(ticker):
    """Return {"price": float, "change": float|None} or None on failure."""
    try:
        url = (
            "https://iss.moex.com/iss/engines/stock/markets/shares"
            "/boards/TQBR/securities/{}.json".format(ticker)
        )
        r = requests.get(url, params={
            "iss.meta": "off",
            "iss.only": "marketdata",
            "marketdata.columns": "SECID,LAST,LASTTOPREVPRICE",
        }, timeout=8)
        r.raise_for_status()
        rows = r.json().get("marketdata", {}).get("data", [])
        if rows and rows[0][1] is not None:
            return {"price": rows[0][1], "change": rows[0][2]}
    except Exception as e:
        print("MOEX price error {}: {}".format(ticker, e))
    return None

def fetch_moex_index():
    """Return current IMOEX value or None."""
    try:
        url = (
            "https://iss.moex.com/iss/engines/stock/markets/index"
            "/boards/SNDX/securities/IMOEX.json"
        )
        r = requests.get(url, params={
            "iss.meta": "off",
            "iss.only": "marketdata",
            "marketdata.columns": "SECID,CURRENTVALUE",
        }, timeout=8)
        r.raise_for_status()
        rows = r.json().get("marketdata", {}).get("data", [])
        if rows and rows[0][1] is not None:
            return rows[0][1]
    except Exception as e:
        print("MOEX index error:", e)
    return None

def market_snapshot():
    """Return formatted current market data string."""
    lines = []

    idx = fetch_moex_index()
    if idx:
        lines.append("📊 Индекс МосБиржи: {:,.0f}".format(idx).replace(",", " "))

    tickers = [
        ("SBER", "Сбер"),
        ("MTSS", "МТС"),
        ("MOEX", "Мосбиржа"),
        ("TMOS", "TMOS"),
        ("LQDT", "LQDT"),
    ]
    for ticker, name in tickers:
        data = fetch_moex_price(ticker)
        if data:
            price = data["price"]
            chg = data.get("change")
            if chg is not None:
                sign = "+" if chg >= 0 else ""
                lines.append("  {} — {:.2f} ₽ ({}{:.1f}%)".format(name, price, sign, chg))
            else:
                lines.append("  {} — {:.2f} ₽".format(name, price))

    if not lines:
        return "Рыночные данные временно недоступны."
    return "\n".join(lines)

# ─── RSS & News ──────────────────────────────────────────────────────────────

def fetch_rss(url, limit=5):
    try:
        r = requests.get(url, headers={"User-Agent": "SashaInvestBot/2.0"}, timeout=12)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item")[:limit]:
            title = clean_text(item.findtext("title"))
            link  = clean_text(item.findtext("link"))
            pub   = clean_text(item.findtext("pubDate"))
            if title:
                items.append({"title": title, "link": link, "date": pub})
        return items
    except Exception as e:
        print("RSS error {}: {}".format(url, e))
        return []

def classify(title):
    t = title.lower()
    if any(w in t for w in ["ключев", "ставк", "денежно-кредит", "инфляц", "цб рф", "банк росс"]):
        return "rate"
    if any(w in t for w in ["офз", "облигац", "долгов", "доходност", "купон"]):
        return "bonds"
    if any(w in t for w in ["дивиденд", "сбербанк", "сбер", " мтс", "московск биржа", " moex"]):
        return "stocks"
    if any(w in t for w in ["индекс мосбирж", "итоги торгов", "рынок акций"]):
        return "market"
    return None

def fetch_important_news():
    """Fetch, classify, deduplicate and return important news list."""
    result = []
    seen = set()
    for source, url in RSS_SOURCES:
        for item in fetch_rss(url):
            cat = classify(item["title"])
            if cat and item["title"] not in seen:
                seen.add(item["title"])
                result.append({**item, "source": source, "cat": cat})
    return result

def format_news_item(i, item):
    lines = ["{}. {}".format(i, item["title"])]
    lines.append("Источник: {}".format(item["source"]))
    if item.get("date"):
        lines.append("Дата: {}".format(item["date"]))
    lines.append(CATEGORY_IMPACT[item["cat"]])
    if item.get("link"):
        lines.append("Ссылка: {}".format(item["link"]))
    return "\n".join(lines)

# ─── Telegram API ────────────────────────────────────────────────────────────

def send_message(chat_id, text, keyboard=None):
    url = "https://api.telegram.org/bot{}/sendMessage".format(BOT_TOKEN)

    def _post(t):
        payload = {"chat_id": chat_id, "text": t}
        if keyboard:
            payload["reply_markup"] = json.dumps(keyboard)
        try:
            requests.post(url, data=payload, timeout=10)
        except Exception as e:
            print("Send error:", e)

    if len(text) <= 3900:
        _post(text)
    else:
        while text:
            part, text = text[:3900], text[3900:]
            _post(part)
            time.sleep(0.4)

def main_keyboard():
    return {
        "keyboard": [
            [{"text": "/morning"}, {"text": "/market"}],
            [{"text": "/portfolio"}, {"text": "/alert"}],
            [{"text": "/income"}, {"text": "/addmoney 50000"}],
            [{"text": "/subscribe"}, {"text": "/help"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }

# ─── Proactive monitoring ────────────────────────────────────────────────────

def check_and_push_news():
    """Every 30 min: push new important news to subscribed chats."""
    global sent_news, last_news_check

    if time.time() - last_news_check < NEWS_INTERVAL:
        return
    last_news_check = time.time()

    if not subscribed_chats:
        return

    news = fetch_important_news()
    new_items = [n for n in news if n["title"] not in sent_news]
    if not new_items:
        return

    priority = {"rate": 0, "bonds": 1, "stocks": 2, "market": 3}
    new_items.sort(key=lambda x: priority.get(x["cat"], 9))

    for item in new_items:
        sent_news.add(item["title"])
    if len(sent_news) > 500:
        sent_news.clear()

    top = new_items[:3]
    msg = "🔔 Важные новости для портфеля\n\n"
    for i, item in enumerate(top, 1):
        msg += format_news_item(i, item) + "\n\n"
    msg += "Полный обзор: /market"

    for chat_id in list(subscribed_chats):
        send_message(chat_id, msg)

def check_morning_briefing():
    """Send morning briefing at 9:00 Moscow time to subscribed chats."""
    global last_morning_date

    now = datetime.utcnow()
    msk_hour = (now.hour + 3) % 24
    today = now.date()

    if msk_hour == 9 and last_morning_date != today and subscribed_chats:
        last_morning_date = today
        msg = "☀️ Утренний обзор\n\n" + cmd_morning()
        for chat_id in list(subscribed_chats):
            send_message(chat_id, msg)

# ─── Command handlers ────────────────────────────────────────────────────────

def cmd_help():
    return (
        "🤖 Family Office Саши\n\n"
        "Команды:\n"
        "/morning — утренний обзор: портфель + рынок + план\n"
        "/portfolio — детальная структура портфеля\n"
        "/market — свежие новости из ЦБ и Мосбиржи\n"
        "/alert — важные сигналы прямо сейчас\n"
        "/income — доход от вклада и купонов\n"
        "/addmoney СУММА — как распределить новые деньги\n"
        "/subscribe — включить авто-оповещения (новости + 9:00 обзор)\n"
        "/unsubscribe — отключить авто-оповещения\n"
        "/rules — правила инвестирования\n"
        "/help — эта справка"
    )

def cmd_morning():
    total, bonds, stocks, liquid = portfolio_totals()
    snap = market_snapshot()

    return (
        "💼 Портфель: {}\n"
        "🏦 Облигации: {} ({}%)\n"
        "📈 Акции и фонды: {} ({}%)\n"
        "💵 Ликвидность: {} ({}%)\n\n"
        "📊 Рынок сейчас:\n"
        "{}\n\n"
        "🎯 План:\n"
        "• Текущие позиции — держать\n"
        "• Новые деньги: 50% ОФЗ · 30% TMOS · 20% LQDT\n"
        "• Не принимать эмоциональных решений\n\n"
        "Новости: /market  |  Сигналы: /alert"
    ).format(
        rub(total),
        rub(bonds), pct(bonds, total),
        rub(stocks), pct(stocks, total),
        rub(liquid), pct(liquid, total),
        snap,
    )

def cmd_portfolio():
    total, bonds, stocks, liquid = portfolio_totals()

    lines = [
        "📊 Портфель Саши\n",
        "Итого: {}\n".format(rub(total)),
        "🏦 Облигации — {} ({}%):".format(rub(bonds), pct(bonds, total)),
        "  ОФЗ 26246 — {}".format(rub(PORTFOLIO["ofz_26246"]["rub"])),
        "  ОФЗ 26252 — {}".format(rub(PORTFOLIO["ofz_26252"]["rub"])),
        "  ОФЗ 26218 — {}\n".format(rub(PORTFOLIO["ofz_26218"]["rub"])),
        "📈 Акции и фонды — {} ({}%):".format(rub(stocks), pct(stocks, total)),
        "  TMOS     — {}".format(rub(PORTFOLIO["tmos"]["rub"])),
        "  Сбер     — {}".format(rub(PORTFOLIO["sber"]["rub"])),
        "  МТС      — {}".format(rub(PORTFOLIO["mts"]["rub"])),
        "  Мосбиржа — {}\n".format(rub(PORTFOLIO["moex_s"]["rub"])),
        "💵 Ликвидность — {} ({}%):".format(rub(liquid), pct(liquid, total)),
        "  Вклад ПСБ — {}".format(rub(PORTFOLIO["psb"]["rub"])),
        "  LQDT      — {}\n".format(rub(PORTFOLIO["lqdt"]["rub"])),
        "Профиль: умеренно-консервативный.",
        "Риск: средний-низкий.",
    ]
    return "\n".join(lines)

def cmd_market():
    snap = market_snapshot()
    news = fetch_important_news()

    header = "📰 Рыночный обзор\n\n{}\n\n".format(snap)

    if not news:
        return (
            header
            + "Источники: Банк России, Московская биржа.\n"
            + "Важных новостей по портфелю не найдено.\n\n"
            + "Рекомендация: изменений не требуется."
        )

    lines = [header + "Источники: Банк России, Московская биржа.\n"]
    for i, item in enumerate(news[:5], 1):
        lines.append(format_news_item(i, item))
        lines.append("")

    lines.append(
        "Итог:\n"
        "ОФЗ — держать · TMOS — докупать планово · LQDT — резерв\n"
        "Эмоциональных решений не принимать."
    )
    return "\n".join(lines)

def cmd_alert():
    news = fetch_important_news()

    if not news:
        return (
            "🔔 Активные сигналы\n\n"
            "🟢 Существенных событий не обнаружено.\n\n"
            "Отслеживаю:\n"
            "• Решения ЦБ по ключевой ставке\n"
            "• Доходности ОФЗ\n"
            "• Дивиденды Сбера, МТС, Мосбиржи\n"
            "• Движения рынка\n\n"
            "Изменений в портфеле не требуется.\n"
            "Полный обзор: /market"
        )

    high  = [n for n in news if n["cat"] in ("rate", "bonds")]
    med   = [n for n in news if n["cat"] in ("stocks", "market")]

    msg = "🔔 Активные сигналы\n\n"

    if high:
        msg += "🔴 Высокий приоритет:\n"
        for item in high[:2]:
            msg += "• {}\n  {}\n".format(item["title"], CATEGORY_IMPACT[item["cat"]])
        msg += "\n"

    if med:
        msg += "🟡 Средний приоритет:\n"
        for item in med[:2]:
            msg += "• {}\n".format(item["title"])
        msg += "\n"

    msg += (
        "Решение:\n"
        "Оцени влияние новости, затем принимай решение.\n"
        "Детали: /market"
    )
    return msg

def cmd_income():
    psb = PORTFOLIO["psb"]["rub"]
    psb_income = psb * 0.20 * 210 / 365

    bond_lines = []
    total_bond_income = 0.0
    for key, yield_rate in BOND_YIELDS.items():
        amt = PORTFOLIO[key]["rub"]
        inc = amt * yield_rate
        total_bond_income += inc
        bond_lines.append(
            "  {} (~{:.0f}%): ~{}".format(
                PORTFOLIO[key]["label"], yield_rate * 100, rub(inc)
            )
        )

    return (
        "💸 Доходы портфеля\n\n"
        "🏦 Вклад ПСБ (20%, 210 дней):\n"
        "  Вложено: {}\n"
        "  Доход за срок: ~{}\n\n"
        "🏦 Купоны ОФЗ (прогноз на год):\n"
        "{}\n"
        "  Итого купоны: ~{}\n\n"
        "📊 Итого пассивный доход: ~{}\n\n"
        "Примечание: без НДФЛ, реинвестирования\n"
        "и переоценки цен облигаций."
    ).format(
        rub(psb),
        rub(psb_income),
        "\n".join(bond_lines),
        rub(total_bond_income),
        rub(psb_income + total_bond_income),
    )

def cmd_addmoney(amount_str):
    try:
        amount = int(amount_str.replace(" ", "").replace(",", ""))
        if amount <= 0:
            raise ValueError
        bonds_add = int(amount * 0.50)
        tmos_add  = int(amount * 0.30)
        lqdt_add  = amount - bonds_add - tmos_add

        return (
            "💰 Новые деньги: {}\n\n"
            "Распределение:\n"
            "🏦 ОФЗ / облигации — {} (50%)\n"
            "📈 TMOS             — {} (30%)\n"
            "💵 LQDT             — {} (20%)\n\n"
            "Стратегия: умеренно-консервативная.\n"
            "Приоритет ОФЗ: 26246 ≥ 26252 > новые выпуски.\n"
            "ОФЗ 26218 не докупать."
        ).format(rub(amount), rub(bonds_add), rub(tmos_add), rub(lqdt_add))
    except Exception:
        return "Не понял сумму. Пример: /addmoney 50000"

def cmd_subscribe(chat_id):
    subscribed_chats.add(chat_id)
    return (
        "✅ Подписка активирована!\n\n"
        "Что буду присылать:\n"
        "• Важные новости от ЦБ и Мосбиржи (проверка каждые 30 мин)\n"
        "• Утренний обзор в 9:00 по Москве\n\n"
        "Для отключения: /unsubscribe"
    )

def cmd_unsubscribe(chat_id):
    subscribed_chats.discard(chat_id)
    return "🔕 Авто-оповещения отключены. Включить: /subscribe"

def cmd_rules():
    return (
        "📜 Правила Саши\n\n"
        "1. Действовать только по плану.\n"
        "2. Новые деньги: 50% ОФЗ · 30% TMOS · 20% LQDT.\n"
        "3. ОФЗ 26218 не докупать.\n"
        "4. Отдельные акции не увеличивать сверх стратегии.\n"
        "5. Проверять портфель раз в месяц, не чаще.\n"
        "6. Не принимать эмоциональных решений.\n"
        "7. Цель: долгосрочный рост капитала с контролем риска."
    )

# ─── Main router ─────────────────────────────────────────────────────────────

def answer(text, chat_id):
    text = text.strip()

    if text in ("/start", "/help"):
        return cmd_help()
    if text == "/morning":
        return cmd_morning()
    if text == "/portfolio":
        return cmd_portfolio()
    if text == "/market":
        return cmd_market()
    if text == "/alert":
        return cmd_alert()
    if text == "/income":
        return cmd_income()
    if text == "/rules":
        return cmd_rules()
    if text == "/subscribe":
        return cmd_subscribe(chat_id)
    if text == "/unsubscribe":
        return cmd_unsubscribe(chat_id)
    if text.startswith("/addmoney"):
        parts = text.split(maxsplit=1)
        return cmd_addmoney(parts[1] if len(parts) > 1 else "")

    # Legacy aliases — keep backward compatibility
    if text in ("/dashboard", "/today", "/action"):
        return cmd_morning()
    if text in ("/advice", "/signal", "/watch", "/priority"):
        return cmd_alert()
    if text == "/meeting":
        return cmd_portfolio()
    if text in ("/year", "/psb"):
        return cmd_income()
    if text == "/rebalance":
        return cmd_addmoney("50000")

    return "Команда не найдена. Напиши /help"

# ─── Main loop ───────────────────────────────────────────────────────────────

print("SashaInvestBot v2 started")

while True:
    try:
        if not BOT_TOKEN:
            print("BOT_TOKEN is missing — check environment variables")
            time.sleep(10)
            continue

        check_and_push_news()
        check_morning_briefing()

        url = "https://api.telegram.org/bot{}/getUpdates?offset={}".format(
            BOT_TOKEN, last_update_id + 1
        )
        updates = requests.get(url, timeout=30).json()

        if updates.get("ok"):
            for update in updates.get("result", []):
                last_update_id = update["update_id"]
                msg = update.get("message")
                if not msg:
                    continue
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")
                if text:
                    send_message(chat_id, answer(text, chat_id), main_keyboard())

    except Exception as e:
        print("Error:", e)

    time.sleep(2)
