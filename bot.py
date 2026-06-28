import os
import re
import time
import json
import threading
import requests
import xml.etree.ElementTree as ET
from html import unescape
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN")

last_update_id = 0
sent_news = set()
last_news_check = 0
last_morning_date = None
last_evening_date = None
NEWS_INTERVAL = 1800
subscribed_chats = set()

_cache = {}
CACHE_TTL = 300  # 5-minute cache for market data

# ─── Portfolio ────────────────────────────────────────────────────────────────

PORTFOLIO = {
    "psb":       {"rub": 50000,  "label": "Вклад ПСБ",  "group": "liquid"},
    "ofz_26246": {"rub": 25230,  "label": "ОФЗ 26246",  "group": "bonds"},
    "ofz_26252": {"rub": 10208,  "label": "ОФЗ 26252",  "group": "bonds"},
    "ofz_26218": {"rub": 34830,  "label": "ОФЗ 26218",  "group": "bonds"},
    "tmos":      {"rub": 24998,  "label": "TMOS",        "group": "stocks"},
    "sber":      {"rub": 19856,  "label": "Сбер",        "group": "stocks"},
    "mts":       {"rub": 8680,   "label": "МТС",         "group": "stocks"},
    "moex_s":    {"rub": 9591,   "label": "Мосбиржа",    "group": "stocks"},
    "lqdt":      {"rub": 16607,  "label": "LQDT",        "group": "liquid"},
}

BOND_YIELDS = {
    "ofz_26246": 0.120,
    "ofz_26252": 0.125,
    "ofz_26218": 0.085,
}

UPDATE_ALIASES = {
    "psb": "psb",
    "sber": "sber", "сбер": "sber",
    "mts": "mts", "mtss": "mts", "мтс": "mts",
    "moex": "moex_s", "moex_s": "moex_s", "мосбиржа": "moex_s",
    "tmos": "tmos", "тмос": "tmos",
    "lqdt": "lqdt",
    "ofz_26246": "ofz_26246", "26246": "ofz_26246",
    "ofz_26252": "ofz_26252", "26252": "ofz_26252",
    "ofz_26218": "ofz_26218", "26218": "ofz_26218",
}

RSS_SOURCES = [
    ("Банк России",      "https://www.cbr.ru/rss/RssPress"),
    ("Банк России",      "https://www.cbr.ru/rss/eventrss"),
    ("Московская биржа", "https://www.moex.com/export/news.aspx?cat=101"),
]

# Strict regex filters — only news that directly affects this portfolio
CRITICAL_PATTERNS = [
    (r"банк\s+росс.{0,40}(снизил|повысил|сохранил).{0,20}ставк",          "🔴 Решение ЦБ по ставке"),
    (r"ключев.{0,10}ставк.{0,40}(снижен|повышен|сохранен|установлен)",     "🔴 Решение ЦБ по ставке"),
    (r"(сбербанк|сбер).{0,60}дивиденд|дивиденд.{0,60}(сбербанк|сбер)",    "🔴 Дивиденды Сбера"),
    (r"\bмтс\b.{0,60}дивиденд|дивиденд.{0,60}\bмтс\b",                    "🔴 Дивиденды МТС"),
    (r"московск.{0,15}бирж.{0,60}дивиденд|дивиденд.{0,60}московск",       "🔴 Дивиденды Мосбиржи"),
]

IMPORTANT_PATTERNS = [
    (r"ключев.{0,10}ставк",                                                 "⚠️ Ключевая ставка"),
    (r"заседани.{0,40}(банк\s+росс|совет\s+директор)",                     "⚠️ Заседание ЦБ"),
    (r"инфляц.{0,30}(составил|достигл|ускорил|замедлил|снизил|вырос)",     "⚠️ Инфляция"),
    (r"(офз|минфин).{0,40}(аукцион|доходност|размещен)",                   "⚠️ Новости ОФЗ"),
    (r"денежно.кредитн.{0,20}политик",                                      "⚠️ Политика ЦБ"),
]

# ─── Helpers ─────────────────────────────────────────────────────────────────

def rub(x):
    return "{:,.0f} ₽".format(x).replace(",", " ")

def pct(value, total):
    return round(value / total * 100, 1) if total else 0.0

def chg_str(chg):
    if chg is None:
        return ""
    return " ({}{:.1f}%)".format("+" if chg >= 0 else "", chg)

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
    for ch in ("\n", "\r", "\t"):
        text = text.replace(ch, " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()

# ─── Market data (parallel fetch + cache) ────────────────────────────────────

def _get(url, params=None, timeout=5):
    r = requests.get(url, params=params, timeout=timeout,
                     headers={"User-Agent": "SashaInvestBot/3.0"})
    r.raise_for_status()
    return r

def fetch_moex_price(ticker):
    try:
        rows = _get(
            "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{}.json".format(ticker),
            {"iss.meta": "off", "iss.only": "marketdata", "marketdata.columns": "SECID,LAST,LASTTOPREVPRICE"}
        ).json().get("marketdata", {}).get("data", [])
        if rows and rows[0][1] is not None:
            return {"price": rows[0][1], "change": rows[0][2]}
    except Exception as e:
        print("Stock {} error: {}".format(ticker, e))
    return None

def fetch_ofz_price(isin):
    try:
        rows = _get(
            "https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQOB/securities/{}.json".format(isin),
            {"iss.meta": "off", "iss.only": "marketdata", "marketdata.columns": "SECID,LAST,LASTTOPREVPRICE"}
        ).json().get("marketdata", {}).get("data", [])
        if rows and rows[0][1] is not None:
            return {"price_pct": rows[0][1], "change": rows[0][2]}
    except Exception as e:
        print("OFZ {} error: {}".format(isin, e))
    return None

def fetch_moex_index():
    try:
        rows = _get(
            "https://iss.moex.com/iss/engines/stock/markets/index/boards/SNDX/securities/IMOEX.json",
            {"iss.meta": "off", "iss.only": "marketdata", "marketdata.columns": "SECID,CURRENTVALUE,LASTTOPREVPRICE"}
        ).json().get("marketdata", {}).get("data", [])
        if rows and rows[0][1] is not None:
            return {"value": rows[0][1], "change": rows[0][2] if len(rows[0]) > 2 else None}
    except Exception as e:
        print("Index error:", e)
    return None

def fetch_cbr_rates():
    try:
        root = ET.fromstring(_get("https://www.cbr.ru/scripts/XML_daily.asp", timeout=8).content)
        rates = {}
        for v in root.findall("Valute"):
            code = v.findtext("CharCode")
            if code in ("USD", "EUR"):
                val = (v.findtext("Value") or "").replace(",", ".")
                nom = int(v.findtext("Nominal") or "1")
                try:
                    rates[code] = float(val) / nom
                except:
                    pass
        return rates
    except Exception as e:
        print("CBR rates error:", e)
        return {}

def fetch_key_rate():
    try:
        for item in fetch_rss_raw("https://www.cbr.ru/rss/RssPress", limit=20):
            t = item["title"].lower()
            if "ключев" in t and "ставк" in t:
                m = re.search(r"(\d{1,2})[,\.](\d{2})\s*%", item["title"])
                if m:
                    return float(m.group(1) + "." + m.group(2))
    except Exception as e:
        print("Key rate error:", e)
    return None

def fetch_all_market_data():
    """Fetch all market data in parallel threads, cache 5 min."""
    now = time.time()
    if "market" in _cache and now - _cache["market"]["ts"] < CACHE_TTL:
        return _cache["market"]["val"]

    results = {}
    lock = threading.Lock()

    def run(key, fn):
        try:
            val = fn()
        except Exception as e:
            print("fetch {} error: {}".format(key, e))
            val = None
        with lock:
            results[key] = val

    tasks = [
        ("index",        fetch_moex_index),
        ("cbr",          fetch_cbr_rates),
        ("key_rate",     fetch_key_rate),
        ("SBER",         lambda: fetch_moex_price("SBER")),
        ("MTSS",         lambda: fetch_moex_price("MTSS")),
        ("MOEX",         lambda: fetch_moex_price("MOEX")),
        ("TMOS",         lambda: fetch_moex_price("TMOS")),
        ("LQDT",         lambda: fetch_moex_price("LQDT")),
        ("SU26246RMFS1", lambda: fetch_ofz_price("SU26246RMFS1")),
        ("SU26252RMFS9", lambda: fetch_ofz_price("SU26252RMFS9")),
        ("SU26218RMFS0", lambda: fetch_ofz_price("SU26218RMFS0")),
    ]

    threads = [threading.Thread(target=run, args=(k, fn), daemon=True) for k, fn in tasks]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=12)

    data = {
        "index":   results.get("index"),
        "cbr":     results.get("cbr") or {},
        "key_rate": results.get("key_rate"),
        "stocks":  {k: results.get(k) for k in ["SBER", "MTSS", "MOEX", "TMOS", "LQDT"]},
        "ofz":     {k: results.get(k) for k in ["SU26246RMFS1", "SU26252RMFS9", "SU26218RMFS0"]},
    }
    _cache["market"] = {"ts": now, "val": data}
    return data

# ─── RSS & News ──────────────────────────────────────────────────────────────

def fetch_rss_raw(url, limit=10):
    try:
        root = ET.fromstring(_get(url, timeout=10).content)
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

def classify_news(title):
    t = title.lower()
    for pattern, label in CRITICAL_PATTERNS:
        if re.search(pattern, t):
            return ("critical", label)
    for pattern, label in IMPORTANT_PATTERNS:
        if re.search(pattern, t):
            return ("important", label)
    return None

def fetch_portfolio_news():
    result, seen = [], set()
    for source, url in RSS_SOURCES:
        for item in fetch_rss_raw(url):
            if item["title"] in seen:
                continue
            seen.add(item["title"])
            cat = classify_news(item["title"])
            if cat:
                result.append({**item, "source": source, "priority": cat[0], "label": cat[1]})
    result.sort(key=lambda x: 0 if x["priority"] == "critical" else 1)
    return result

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

def send_typing(chat_id):
    try:
        requests.post(
            "https://api.telegram.org/bot{}/sendChatAction".format(BOT_TOKEN),
            data={"chat_id": chat_id, "action": "typing"}, timeout=4)
    except:
        pass

def main_keyboard():
    return {
        "keyboard": [
            [{"text": "/morning"}, {"text": "/news"}],
            [{"text": "/portfolio"}, {"text": "/income"}],
            [{"text": "/addmoney 50000"}, {"text": "/subscribe"}],
            [{"text": "/help"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }

# ─── Proactive monitoring ─────────────────────────────────────────────────────

def check_and_push_news():
    global sent_news, last_news_check
    if time.time() - last_news_check < NEWS_INTERVAL:
        return
    last_news_check = time.time()
    if not subscribed_chats:
        return

    news = fetch_portfolio_news()
    new_critical = [n for n in news if n["priority"] == "critical" and n["title"] not in sent_news]
    if not new_critical:
        return

    for item in new_critical:
        sent_news.add(item["title"])
    if len(sent_news) > 500:
        sent_news.clear()

    for item in new_critical[:2]:
        msg = (
            "🚨 Важное событие!\n\n"
            "{}\n{}\n\n"
            "Источник: {}\n"
        ).format(item["label"], item["title"], item["source"])
        if item.get("link"):
            msg += "Ссылка: {}\n\n".format(item["link"])
        msg += "Детали и рекомендация: /news"
        for chat_id in list(subscribed_chats):
            send_message(chat_id, msg)

def check_morning_briefing():
    global last_morning_date
    now = datetime.utcnow()
    today = now.date()
    if (now.hour + 3) % 24 == 9 and last_morning_date != today and subscribed_chats:
        last_morning_date = today
        msg = "☀️ Доброе утро!\n\n" + cmd_morning()
        for chat_id in list(subscribed_chats):
            send_message(chat_id, msg)

def check_evening_briefing():
    global last_evening_date
    now = datetime.utcnow()
    today = now.date()
    if (now.hour + 3) % 24 == 19 and last_evening_date != today and subscribed_chats:
        last_evening_date = today
        for chat_id in list(subscribed_chats):
            send_message(chat_id, cmd_evening())

# ─── Commands ─────────────────────────────────────────────────────────────────

def cmd_morning():
    total, bonds, stocks, liquid = portfolio_totals()
    md = fetch_all_market_data()

    lines = []

    # Portfolio summary
    lines.append("💼 Портфель: {}".format(rub(total)))
    lines.append("🏦 Облигации:   {} ({}%)".format(rub(bonds),  pct(bonds,  total)))
    lines.append("📈 Акции/фонды: {} ({}%)".format(rub(stocks), pct(stocks, total)))
    lines.append("💵 Ликвидность: {} ({}%)".format(rub(liquid), pct(liquid, total)))
    lines.append("")

    # Key indicators
    cbr = md.get("cbr", {})
    kr  = md.get("key_rate")
    parts = []
    if kr:
        parts.append("Ставка ЦБ: {}%".format(kr))
    if "USD" in cbr:
        parts.append("$ {:.2f}".format(cbr["USD"]))
    if "EUR" in cbr:
        parts.append("€ {:.2f}".format(cbr["EUR"]))
    if parts:
        lines.append("🏛 " + "  |  ".join(parts))
        lines.append("")

    # Index + stocks
    idx = md.get("index")
    if idx and idx.get("value"):
        lines.append("📊 Индекс МосБиржи: {:,.0f}{}".format(
            idx["value"], chg_str(idx.get("change"))).replace(",", " "))

    st = md.get("stocks", {})
    for ticker, name in [("SBER","Сбер"), ("MTSS","МТС"), ("MOEX","Мосбиржа"), ("TMOS","TMOS"), ("LQDT","LQDT")]:
        d = st.get(ticker)
        if d:
            lines.append("  {} — {:.2f} ₽{}".format(name, d["price"], chg_str(d.get("change"))))

    # OFZ prices
    ofz = md.get("ofz", {})
    ofz_rows = []
    for isin, name in [("SU26246RMFS1","26246"), ("SU26252RMFS9","26252"), ("SU26218RMFS0","26218")]:
        d = ofz.get(isin)
        if d:
            ofz_rows.append("  ОФЗ {} — {:.1f}% ({:.0f} ₽){}".format(
                name, d["price_pct"], d["price_pct"] * 10, chg_str(d.get("change"))))
    if ofz_rows:
        lines.append("🏦 ОФЗ:")
        lines.extend(ofz_rows)

    lines.append("")

    # Top news (critical only)
    news = fetch_portfolio_news()
    critical = [n for n in news if n["priority"] == "critical"]
    if critical:
        lines.append("🚨 Срочно:")
        for n in critical[:2]:
            lines.append("• {} — {}".format(n["label"], n["title"]))
        lines.append("")
    elif news:
        lines.append("📰 {}".format(news[0]["title"][:80]))
        lines.append("")

    lines.append("🎯 Держать позиции · TMOS докупать планово")
    lines.append("Новые деньги → /addmoney СУММА  |  Все новости → /news")

    return "\n".join(lines)

def cmd_evening():
    md = fetch_all_market_data()
    lines = ["🌆 Итоги дня\n"]

    idx = md.get("index")
    if idx and idx.get("value"):
        lines.append("📊 Индекс МосБиржи: {:,.0f}{}".format(
            idx["value"], chg_str(idx.get("change"))).replace(",", " "))

    st = md.get("stocks", {})
    for ticker, name in [("SBER","Сбер"), ("MTSS","МТС"), ("MOEX","Мосбиржа"), ("TMOS","TMOS"), ("LQDT","LQDT")]:
        d = st.get(ticker)
        if d:
            lines.append("  {} — {:.2f} ₽{}".format(name, d["price"], chg_str(d.get("change"))))

    news = fetch_portfolio_news()
    critical = [n for n in news if n["priority"] == "critical"]
    if critical:
        lines.append("\n🚨 Требует внимания:")
        for n in critical[:2]:
            lines.append("• {} — {}".format(n["label"], n["title"]))
        lines.append("\nЧто делать: /news")
    else:
        lines.append("\n✅ Критических событий нет. Изменений не требуется.")

    return "\n".join(lines)

def cmd_portfolio():
    total, bonds, stocks, liquid = portfolio_totals()
    md = fetch_all_market_data()
    st  = md.get("stocks", {})
    ofz = md.get("ofz", {})

    lines = ["📊 Портфель Саши", "Итого: {}\n".format(rub(total))]

    lines.append("🏦 Облигации — {} ({}%):".format(rub(bonds), pct(bonds, total)))
    for key, isin, name in [
        ("ofz_26246", "SU26246RMFS1", "ОФЗ 26246"),
        ("ofz_26252", "SU26252RMFS9", "ОФЗ 26252"),
        ("ofz_26218", "SU26218RMFS0", "ОФЗ 26218"),
    ]:
        d = ofz.get(isin)
        extra = " | цена {:.1f}% ({:.0f} ₽){}".format(
            d["price_pct"], d["price_pct"] * 10, chg_str(d.get("change"))) if d else ""
        lines.append("  {} — {}{}".format(name, rub(PORTFOLIO[key]["rub"]), extra))

    lines.append("")
    lines.append("📈 Акции и фонды — {} ({}%):".format(rub(stocks), pct(stocks, total)))
    for key, ticker, name in [
        ("tmos",   "TMOS", "TMOS"),
        ("sber",   "SBER", "Сбер"),
        ("mts",    "MTSS", "МТС"),
        ("moex_s", "MOEX", "Мосбиржа"),
    ]:
        d = st.get(ticker)
        extra = " | {:.2f} ₽{}".format(d["price"], chg_str(d.get("change"))) if d else ""
        lines.append("  {} — {}{}".format(name, rub(PORTFOLIO[key]["rub"]), extra))

    lines.append("")
    lines.append("💵 Ликвидность — {} ({}%):".format(rub(liquid), pct(liquid, total)))
    lines.append("  Вклад ПСБ — {} (20%, 210д)".format(rub(PORTFOLIO["psb"]["rub"])))
    d = st.get("LQDT")
    extra = " | {:.2f} ₽{}".format(d["price"], chg_str(d.get("change"))) if d else ""
    lines.append("  LQDT — {}{}".format(rub(PORTFOLIO["lqdt"]["rub"]), extra))

    lines.append("\nОбновить позицию: /update sber 22000")
    return "\n".join(lines)

def cmd_news():
    news = fetch_portfolio_news()
    if not news:
        return (
            "📰 Важные новости\n\n"
            "🟢 Ничего критического.\n\n"
            "Слежу за:\n"
            "• Решениями ЦБ по ставке\n"
            "• Дивидендами Сбера, МТС, Мосбиржи\n"
            "• Новостями ОФЗ и инфляцией\n\n"
            "Изменений в портфеле не требуется."
        )

    lines = ["📰 Важные новости для портфеля\n"]
    for i, item in enumerate(news[:5], 1):
        lines.append("{}. {}".format(i, item["label"]))
        lines.append("   {}".format(item["title"]))
        if item.get("date"):
            lines.append("   {}".format(item["date"]))
        if item.get("link"):
            lines.append("   {}".format(item["link"]))
        lines.append("")

    critical = [n for n in news if n["priority"] == "critical"]
    if critical:
        lines.append("⚠️ {} критическое — оцени влияние перед действием.".format(len(critical)))
    else:
        lines.append("✅ Критических событий нет. Изменений не требуется.")

    return "\n".join(lines)

def cmd_income():
    psb = PORTFOLIO["psb"]["rub"]
    psb_income = psb * 0.20 * 210 / 365

    bond_lines = []
    bond_total = 0.0
    for key, rate in BOND_YIELDS.items():
        amt = PORTFOLIO[key]["rub"]
        inc = amt * rate
        bond_total += inc
        bond_lines.append("  {} (~{:.0f}%): ~{}".format(PORTFOLIO[key]["label"], rate * 100, rub(inc)))

    return (
        "💸 Доходы портфеля\n\n"
        "🏦 Вклад ПСБ (20%, 210 дней):\n"
        "  Вложено: {}\n"
        "  Доход за срок: ~{}\n\n"
        "🏦 Купоны ОФЗ (прогноз на год):\n"
        "{}\n"
        "  Итого: ~{}\n\n"
        "📊 Пассивный доход итого: ~{}\n\n"
        "💡 Дивиденды:\n"
        "  Сбер, МТС, Мосбиржа — бот пришлёт уведомление\n"
        "  при объявлении (включи /subscribe)\n\n"
        "Без учёта НДФЛ и реинвестирования."
    ).format(
        rub(psb), rub(psb_income),
        "\n".join(bond_lines), rub(bond_total),
        rub(psb_income + bond_total),
    )

def cmd_addmoney(args):
    try:
        amount = int(args.replace(" ", "").replace(",", ""))
        if amount <= 0:
            raise ValueError
        b = int(amount * 0.50)
        t = int(amount * 0.30)
        l = amount - b - t
        return (
            "💰 Новые деньги: {}\n\n"
            "🏦 ОФЗ — {} (50%)\n"
            "📈 TMOS — {} (30%)\n"
            "💵 LQDT — {} (20%)\n\n"
            "Приоритет ОФЗ: 26246 ≥ 26252 > новые выпуски.\n"
            "ОФЗ 26218 не докупать."
        ).format(rub(amount), rub(b), rub(t), rub(l))
    except:
        return "Пример: /addmoney 50000"

def cmd_update(args):
    parts = args.strip().split()
    if len(parts) < 2:
        return (
            "Формат: /update ПОЗИЦИЯ СУММА\n\n"
            "Примеры:\n"
            "/update sber 22000\n"
            "/update 26246 27000\n"
            "/update tmos 28000\n"
            "/update lqdt 18000\n"
            "/update psb 55000"
        )
    key = UPDATE_ALIASES.get(parts[0].lower())
    if not key:
        return "Не нашла позицию '{}'. Пример: /update sber 22000".format(parts[0])
    try:
        amount = int(parts[1].replace(",", ""))
        if amount < 0:
            raise ValueError
    except:
        return "Не понял сумму. Пример: /update sber 22000"

    old = PORTFOLIO[key]["rub"]
    PORTFOLIO[key]["rub"] = amount
    diff = amount - old
    total, _, _, _ = portfolio_totals()
    return "✅ {} → {}\nИзменение: {}{}\nПортфель: {}".format(
        PORTFOLIO[key]["label"], rub(amount),
        "+" if diff >= 0 else "", rub(diff), rub(total))

def cmd_subscribe(chat_id):
    subscribed_chats.add(chat_id)
    return (
        "✅ Подписка активирована!\n\n"
        "Буду присылать:\n"
        "☀️ 9:00 МСК — утренний обзор\n"
        "🌆 19:00 МСК — итоги дня\n"
        "🚨 В любое время — критические события\n"
        "   (решение ЦБ, дивиденды Сбера/МТС/Мосбиржи)\n\n"
        "Отключить: /unsubscribe"
    )

def cmd_unsubscribe(chat_id):
    subscribed_chats.discard(chat_id)
    return "🔕 Оповещения отключены. Включить: /subscribe"

def cmd_rules():
    return (
        "📜 Правила Саши\n\n"
        "1. Действовать только по плану.\n"
        "2. Новые деньги: 50% ОФЗ · 30% TMOS · 20% LQDT.\n"
        "3. ОФЗ 26218 не докупать.\n"
        "4. Акции не наращивать сверх стратегии.\n"
        "5. Проверять портфель раз в месяц.\n"
        "6. Не принимать решений на эмоциях.\n"
        "7. Цель: долгосрочный рост с контролем риска."
    )

def cmd_help():
    return (
        "🤖 Family Office Саши\n\n"
        "/morning — обзор: ставка + курс + портфель + цены\n"
        "/news — только важные новости для портфеля\n"
        "/portfolio — состав с текущими ценами\n"
        "/income — вклад, купоны, дивиденды\n"
        "/addmoney СУММА — распределить новые деньги\n"
        "/update ПОЗИЦИЯ СУММА — обновить позицию\n"
        "/subscribe — авто: 9:00, 19:00 и срочные новости\n"
        "/unsubscribe — отключить\n"
        "/rules — правила инвестирования\n"
        "/help — эта справка"
    )

# ─── Router ───────────────────────────────────────────────────────────────────

def answer(text, chat_id):
    t = text.strip()
    if t in ("/start", "/help"):          return cmd_help()
    if t == "/morning":                    return cmd_morning()
    if t == "/portfolio":                  return cmd_portfolio()
    if t in ("/news", "/market", "/alert"): return cmd_news()
    if t == "/income":                     return cmd_income()
    if t == "/rules":                      return cmd_rules()
    if t == "/subscribe":                  return cmd_subscribe(chat_id)
    if t == "/unsubscribe":                return cmd_unsubscribe(chat_id)
    if t.startswith("/addmoney"):
        parts = t.split(maxsplit=1)
        return cmd_addmoney(parts[1] if len(parts) > 1 else "")
    if t.startswith("/update"):
        parts = t.split(maxsplit=1)
        return cmd_update(parts[1] if len(parts) > 1 else "")
    # Legacy aliases
    if t in ("/dashboard", "/today", "/action"): return cmd_morning()
    if t in ("/advice", "/signal", "/watch", "/priority"): return cmd_news()
    if t in ("/meeting",):               return cmd_portfolio()
    if t in ("/year", "/psb"):           return cmd_income()
    if t == "/rebalance":                return cmd_addmoney("50000")
    return "Команда не найдена. Напиши /help"

# ─── Main loop ────────────────────────────────────────────────────────────────

print("SashaInvestBot v3 started")

while True:
    try:
        if not BOT_TOKEN:
            print("BOT_TOKEN missing")
            time.sleep(10)
            continue

        check_and_push_news()
        check_morning_briefing()
        check_evening_briefing()

        url = "https://api.telegram.org/bot{}/getUpdates?offset={}".format(
            BOT_TOKEN, last_update_id + 1)
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
                    send_typing(chat_id)
                    send_message(chat_id, answer(text, chat_id), main_keyboard())

    except Exception as e:
        print("Error:", e)

    time.sleep(2)
