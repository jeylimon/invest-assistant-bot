import os
import re
import time
import json
import threading
import requests
import xml.etree.ElementTree as ET
from html import unescape
from datetime import datetime, date

BOT_TOKEN = os.environ.get("BOT_TOKEN")

last_update_id = 0
sent_news = set()
last_news_check = 0
last_morning_date = None
last_evening_date = None
last_cutoff_alert_date = None
last_payment_reminder_date = None
last_price_alert_date = None
NEWS_INTERVAL = 1800
subscribed_chats = set()

_cache = {}
CACHE_TTL = 300

DATA_DIR      = "/data"
SUBS_FILE     = "/data/subscriptions.json"
NEWS_FILE     = "/data/sent_news.json"
PORTFOLIO_FILE = "/data/portfolio.json"

# ─── Portfolio ────────────────────────────────────────────────────────────────

PORTFOLIO = {
    "psb":       {"rub": 50000,  "units": None, "ticker": None,   "isin": None,           "coupon": None,  "group": "liquid", "label": "Вклад ПСБ (20%, 210д)"},
    "ofz_26246": {"rub": 25230,  "units": 29,   "ticker": None,   "isin": "SU26246RMFS7", "coupon": 59.84, "group": "bonds",  "label": "ОФЗ 26246 (купон 12%)"},
    "ofz_26252": {"rub": 10208,  "units": 11,   "ticker": None,   "isin": "SU26252RMFS5", "coupon": 62.33, "group": "bonds",  "label": "ОФЗ 26252 (купон 12.5%)"},
    "ofz_26218": {"rub": 33210,  "units": 41,   "ticker": None,   "isin": "RU000A0JVW48", "coupon": 42.38, "group": "bonds",  "label": "ОФЗ 26218 (купон 8.5%)"},
    "tmos":      {"rub": 1076,   "units": 195,  "ticker": "TMOS", "isin": None,           "coupon": None,  "group": "stocks", "label": "TMOS"},
    "sber":      {"rub": 18980,  "units": 65,   "ticker": "SBER", "isin": None,           "coupon": None,  "group": "stocks", "label": "Сбер"},
    "mts":       {"rub": 8680,   "units": 40,   "ticker": "MTSS", "isin": None,           "coupon": None,  "group": "stocks", "label": "МТС"},
    "moex_s":    {"rub": 9591,   "units": 60,   "ticker": "MOEX", "isin": None,           "coupon": None,  "group": "stocks", "label": "Мосбиржа"},
    "lqdt":      {"rub": 0,      "units": 0,    "ticker": "LQDT", "isin": None,           "coupon": None,  "group": "liquid", "label": "LQDT (резерв)"},
}

PAYMENT_CALENDAR = [
    {"date": date(2026,  7, 23), "name": "МТС",        "type": "div",    "amount": 1400.00,  "note": "35 ₽/акц × 40 шт"},
    {"date": date(2026,  7, 23), "name": "Мосбиржа",   "type": "div",    "amount": 1174.20,  "note": "19.57 ₽ × 60 шт ✅ одобрено СД"},
    {"date": date(2026,  8,  3), "name": "Сбер",       "type": "div",    "amount": 2446.60,  "note": "37.64 ₽ × 65 шт"},
    {"date": date(2026,  9, 12), "name": "ОФЗ 26246",  "type": "coupon", "amount": 1735.36,  "note": "59.84 ₽ × 29 шт"},
    {"date": date(2026,  9, 25), "name": "ОФЗ 26218",  "type": "coupon", "amount": 1737.58,  "note": "42.38 ₽ × 41 шт"},
    {"date": date(2026, 10, 22), "name": "ОФЗ 26252",  "type": "coupon", "amount":  685.63,  "note": "62.33 ₽ × 11 шт"},
    {"date": date(2027,  3, 12), "name": "ОФЗ 26246",  "type": "coupon", "amount": 1735.36,  "note": "59.84 ₽ × 29 шт"},
    {"date": date(2027,  3, 25), "name": "ОФЗ 26218",  "type": "coupon", "amount": 1737.58,  "note": "42.38 ₽ × 41 шт"},
    {"date": date(2027,  4, 22), "name": "ОФЗ 26252",  "type": "coupon", "amount":  685.63,  "note": "62.33 ₽ × 11 шт"},
]

CUTOFF_ALERTS = [
    {"buy_before": date(2026, 7,  8), "name": "МТС",      "status": "✅ 40 шт — дивиденд обеспечен"},
    {"buy_before": date(2026, 7,  8), "name": "Мосбиржа", "status": "✅ 60 шт — дивиденд обеспечен"},
    {"buy_before": date(2026, 7, 17), "name": "Сбер",     "status": "⚠️ +3 шт (до 68 по плану) → +113 ₽"},
]

TODO_ITEMS = [
    {"priority": 1, "deadline": date(2026, 7, 17), "action": "Сбер: купить ещё 3 шт до 17.07 → +113 ₽ дивиденд",     "amount": 900},
    {"priority": 2, "deadline": None,              "action": "TMOS: докупить ~3 837 шт (~23 900 ₽)",                  "amount": 23900},
    {"priority": 3, "deadline": None,              "action": "LQDT: купить ~8 303 шт (~16 600 ₽) — денежный резерв",  "amount": 16600},
    {"priority": 4, "deadline": None,              "action": "ОФЗ 26218: купить ещё 2 шт (~1 620 ₽)",                 "amount": 1620},
]

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
    "iis": "iis", "ии": "iis",
}

RSS_SOURCES = [
    ("Банк России",      "https://www.cbr.ru/rss/RssPress"),
    ("Банк России",      "https://www.cbr.ru/rss/eventrss"),
    ("Московская биржа", "https://www.moex.com/export/news.aspx?cat=101"),
    ("РБК Инвестиции",   "https://rssexport.rbc.ru/rbcnews/news/30/full.rss"),
    ("ТАСС Экономика",   "https://tass.ru/rss/v2.xml"),
]

CRITICAL_PATTERNS = [
    (r"банк\s+росс.{0,60}(снизил|повысил|сохранил|снизить|повысить|сохранить).{0,30}ставк", "🔴 Решение ЦБ по ставке"),
    (r"банк\s+росс.{0,40}принял\s+решение.{0,40}ставк",                               "🔴 Решение ЦБ по ставке"),
    (r"ключев.{0,10}ставк.{0,40}(снижен|повышен|сохранен|установлен|до\s+\d)",        "🔴 Решение ЦБ по ставке"),
    (r"(сбербанк|сбер).{0,60}дивиденд|дивиденд.{0,60}(сбербанк|сбер)",               "🔴 Дивиденды Сбера"),
    (r"(сбербанк|сбер).{0,60}(рекомендовал|утвердил).{0,40}дивиденд",                 "🔴 Дивиденды Сбера"),
    (r"\bмтс\b.{0,60}дивиденд|дивиденд.{0,60}\bмтс\b",                               "🔴 Дивиденды МТС"),
    (r"\bмтс\b.{0,60}(рекомендовал|утвердил).{0,40}дивиденд",                         "🔴 Дивиденды МТС"),
    (r"московск.{0,15}бирж.{0,60}дивиденд|дивиденд.{0,60}московск",                  "🔴 Дивиденды Мосбиржи"),
    (r"московск.{0,15}бирж.{0,60}(рекомендовал|утвердил).{0,40}дивиденд",             "🔴 Дивиденды Мосбиржи"),
]

IMPORTANT_PATTERNS = [
    (r"ключев.{0,10}ставк",                                                            "⚠️ Ключевая ставка"),
    (r"заседани.{0,40}(банк\s+росс|совет\s+директор)",                                "⚠️ Заседание ЦБ"),
    (r"инфляц.{0,30}(составил|достигл|ускорил|замедлил|снизил|вырос|за\s+\w+)",       "⚠️ Инфляция"),
    (r"(офз|минфин).{0,40}(аукцион|доходност|размещен|отсечк)",                       "⚠️ Новости ОФЗ"),
    (r"денежно.кредитн.{0,20}политик",                                                 "⚠️ Политика ЦБ"),
    (r"(сбербанк|сбер|мтс|московск.{0,10}бирж).{0,60}(результат|отчёт|отчет|прибыл)", "⚠️ Отчётность эмитента"),
    (r"(рубль|курс\s+доллар|курс\s+евро).{0,40}(упал|вырос|ослаб|укрепил)",           "⚠️ Курс рубля"),
    (r"индекс\s+мосбирж.{0,30}(упал|вырос|снизил|повысил|достиг)",                    "⚠️ Индекс МосБиржи"),
]

# Конкретные рекомендации по каждому типу события
NEWS_ACTIONS = {
    "🔴 Решение ЦБ по ставке": (
        "Снижение ставки → твои ОФЗ вырастут в цене, купоны остаются высокими — держи, не продавай. "
        "Хороший момент докупить ОФЗ по плану: 26218 +2 шт. "
        "Повышение → цена ОФЗ немного упадёт, но купон фиксирован — не паникуй, держи до погашения. "
        "Сохранение → стратегия оптимальна, действий не нужно. Детали: /plan"
    ),
    "🔴 Дивиденды Сбера": (
        "У тебя 65 шт Сбера → дивиденд 2 446 ₽ (выплата 3 авг). "
        "По плану ещё +3 шт до отсечки 17 июля → +113 ₽ к выплате. "
        "Проверь срочные задачи: /plan"
    ),
    "🔴 Дивиденды МТС": (
        "У тебя 40 шт МТС → дивиденд 1 400 ₽ (выплата 23 июл). "
        "Отсечка 8 июля — ты уже в списке, дивиденд обеспечен. "
        "Никаких действий не нужно. Детали: /dividends"
    ),
    "🔴 Дивиденды Мосбиржи": (
        "У тебя 60 шт Мосбиржи → дивиденд 1 174 ₽ (выплата 23 июл). "
        "Отсечка 8 июля — ты уже в списке, дивиденд обеспечен. "
        "Никаких действий не нужно. Детали: /dividends"
    ),
    "⚠️ Ключевая ставка": (
        "Упоминание ставки — жди официального заседания ЦБ. "
        "До объявления решения — никаких движений по портфелю. "
        "После решения проверь: /news"
    ),
    "⚠️ Заседание ЦБ": (
        "Скоро решение по ставке. "
        "Не покупай ОФЗ прямо перед заседанием — цена может измениться. "
        "Дождись итога, затем действуй по плану: /plan"
    ),
    "⚠️ Инфляция": (
        "Высокая инфляция → ЦБ, скорее всего, не будет снижать ставку. "
        "Вклад ПСБ (20%) и ОФЗ с фиксированным купоном частично защищают. "
        "Не перекладывай из ОФЗ в акции на фоне высокой инфляции."
    ),
    "⚠️ Новости ОФЗ": (
        "Рост доходности ОФЗ = снижение цены, но твой купон фиксирован — это не потеря. "
        "Если доходность выросла — выгодный момент докупить ОФЗ 26218 (+2 шт по плану, ~1 620 ₽). "
        "Детали позиций: /portfolio"
    ),
    "⚠️ Политика ЦБ": (
        "Риторика ЦБ меняется — сигнал будущим решениям. "
        "Жёсткая риторика = ставка не снизится скоро → LQDT и вклады выгоднее. "
        "Мягкая риторика → готовься докупать ОФЗ. Пока — придерживайся плана: /plan"
    ),
    "⚠️ Отчётность эмитента": (
        "Следи за прибылью: рост прибыли → дивиденды стабильны или выше. "
        "Сбер: ключевой для тебя (65 шт). МТС: 40 шт. Мосбиржа: 60 шт. "
        "Убыток или падение прибыли → дивиденды под риском. Детали: /dividends"
    ),
    "⚠️ Курс рубля": (
        "Слабый рубль повышает инфляцию → ЦБ удерживает высокую ставку. "
        "Для твоего рублёвого портфеля: ОФЗ и вклады защищают от рублёвой инфляции. "
        "Акций в иностранной валюте у тебя нет — прямого влияния минимум."
    ),
    "⚠️ Индекс МосБиржи": (
        "Падение индекса — не повод продавать акции. "
        "Твои акции (Сбер, МТС, Мосбиржа) — дивидендные, держи за выплаты. "
        "TMOS следует за индексом — при сильном падении можно докупить по плану."
    ),
}

# Целевое распределение портфеля (%)
TARGET_ALLOCATION = {"bonds": 40, "stocks": 35, "liquid": 25}

# Вложения в ИИС за текущий год (обновляй через /update iis СУММА)
IIS_CONTRIBUTION = 131195  # портфель минус вклад ПСБ (ориентировочно)

# ─── State persistence ───────────────────────────────────────────────────────

def load_state():
    global subscribed_chats, sent_news, IIS_CONTRIBUTION
    try:
        with open(SUBS_FILE) as f:
            subscribed_chats = set(json.load(f))
        print("Loaded {} subscriptions".format(len(subscribed_chats)))
    except Exception:
        pass
    try:
        with open(NEWS_FILE) as f:
            sent_news = set(json.load(f))
    except Exception:
        pass
    try:
        with open(PORTFOLIO_FILE) as f:
            saved = json.load(f)
        IIS_CONTRIBUTION = saved.get("iis_contribution", IIS_CONTRIBUTION)
        for key, vals in saved.get("positions", {}).items():
            if key in PORTFOLIO:
                if "rub" in vals:
                    PORTFOLIO[key]["rub"] = vals["rub"]
                if "units" in vals and vals["units"] is not None:
                    PORTFOLIO[key]["units"] = vals["units"]
        print("Loaded portfolio from disk")
    except Exception:
        pass

def save_subscriptions():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SUBS_FILE, "w") as f:
            json.dump(list(subscribed_chats), f)
    except Exception as e:
        print("Save subs error:", e)

def save_sent_news():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        items = list(sent_news)[-300:]
        with open(NEWS_FILE, "w") as f:
            json.dump(items, f)
    except Exception as e:
        print("Save news error:", e)

def save_portfolio():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        positions = {k: {"rub": v["rub"], "units": v["units"]} for k, v in PORTFOLIO.items()}
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump({"iis_contribution": IIS_CONTRIBUTION, "positions": positions}, f)
    except Exception as e:
        print("Save portfolio error:", e)

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

def days_until(d):
    return (d - date.today()).days

def fmt_date(d):
    months = ["янв", "фев", "мар", "апр", "май", "июн",
              "июл", "авг", "сен", "окт", "ноя", "дек"]
    return "{} {}".format(d.day, months[d.month - 1])

# ─── Market data (parallel fetch + cache) ────────────────────────────────────

def _get(url, params=None, timeout=5):
    r = requests.get(url, params=params, timeout=timeout,
                     headers={"User-Agent": "SashaInvestBot/4.0"})
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
        ("SU26246RMFS7", lambda: fetch_ofz_price("SU26246RMFS7")),
        ("SU26252RMFS5", lambda: fetch_ofz_price("SU26252RMFS5")),
        ("RU000A0JVW48", lambda: fetch_ofz_price("RU000A0JVW48")),
    ]

    threads = [threading.Thread(target=run, args=(k, fn), daemon=True) for k, fn in tasks]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=12)

    data = {
        "index":    results.get("index"),
        "cbr":      results.get("cbr") or {},
        "key_rate": results.get("key_rate"),
        "stocks":   {k: results.get(k) for k in ["SBER", "MTSS", "MOEX", "TMOS", "LQDT"]},
        "ofz":      {k: results.get(k) for k in ["SU26246RMFS7", "SU26252RMFS5", "RU000A0JVW48"]},
    }
    _cache["market"] = {"ts": now, "val": data}
    return data

def live_portfolio_value(md):
    """Return dict with live value per key, plus total. Falls back to cost basis when no price."""
    st  = md.get("stocks", {})
    ofz = md.get("ofz", {})

    ofz_map = {
        "ofz_26246": ("SU26246RMFS7", ofz.get("SU26246RMFS7")),
        "ofz_26252": ("SU26252RMFS5", ofz.get("SU26252RMFS5")),
        "ofz_26218": ("RU000A0JVW48", ofz.get("RU000A0JVW48")),
    }
    stock_map = {
        "tmos":   st.get("TMOS"),
        "sber":   st.get("SBER"),
        "mts":    st.get("MTSS"),
        "moex_s": st.get("MOEX"),
        "lqdt":   st.get("LQDT"),
    }

    values = {}
    for key, pos in PORTFOLIO.items():
        units = pos.get("units")
        if key in ofz_map and units:
            _, d = ofz_map[key]
            if d:
                values[key] = d["price_pct"] / 100 * 1000 * units
            else:
                values[key] = pos["rub"]
        elif key in stock_map and units is not None:
            d = stock_map[key]
            if d and units > 0:
                values[key] = d["price"] * units
            else:
                values[key] = pos["rub"]
        else:
            values[key] = pos["rub"]

    return values

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
            [{"text": "/morning"}, {"text": "/evening"}],
            [{"text": "/portfolio"}, {"text": "/news"}],
            [{"text": "/plan"}, {"text": "/income"}],
            [{"text": "/addmoney 3000"}, {"text": "/update"}],
            [{"text": "/subscribe"}, {"text": "/help"}],
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
    save_sent_news()

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

def check_cutoff_alerts():
    global last_cutoff_alert_date
    today = date.today()
    if last_cutoff_alert_date == today or not subscribed_chats:
        return
    urgent = [a for a in CUTOFF_ALERTS if 0 <= days_until(a["buy_before"]) <= 7]
    if not urgent:
        return
    last_cutoff_alert_date = today
    lines = ["⏰ Дедлайн по дивидендам — осталось мало времени!\n"]
    for a in urgent:
        d = days_until(a["buy_before"])
        lines.append("• {} — последний день {} (через {} дн.)".format(
            a["name"], fmt_date(a["buy_before"]), d))
        lines.append("  {}".format(a["status"]))
    lines.append("\nПодробнее: /plan")
    msg = "\n".join(lines)
    for chat_id in list(subscribed_chats):
        send_message(chat_id, msg)

def check_payment_reminders():
    global last_payment_reminder_date
    today = date.today()
    if last_payment_reminder_date == today or not subscribed_chats:
        return
    reminders = [p for p in PAYMENT_CALENDAR if 1 <= days_until(p["date"]) <= 3]
    if not reminders:
        return
    last_payment_reminder_date = today
    lines = ["💰 Скоро выплата на счёт!\n"]
    for p in reminders:
        d = days_until(p["date"])
        icon = "💰" if p["type"] == "div" else "🏦"
        tag = "дивиденд" if p["type"] == "div" else "купон"
        lines.append("{} {} {} — {}".format(icon, fmt_date(p["date"]), p["name"], rub(p["amount"])))
        lines.append("  {} | {}".format(tag, p["note"]))
        lines.append("  Через {} дн. поступят на брокерский счёт.".format(d))
    lines.append("\nПолный календарь: /dividends")
    msg = "\n".join(lines)
    for chat_id in list(subscribed_chats):
        send_message(chat_id, msg)

def check_price_drops():
    global last_price_alert_date
    today = date.today()
    if last_price_alert_date == today or not subscribed_chats:
        return
    now_hour = (datetime.utcnow().hour + 3) % 24
    if now_hour < 18:
        return
    last_price_alert_date = today
    md = fetch_all_market_data()
    st = md.get("stocks", {})
    alerts = []
    for ticker, name in [("SBER", "Сбер"), ("MTSS", "МТС"), ("MOEX", "Мосбиржа"), ("TMOS", "TMOS")]:
        d = st.get(ticker)
        if d and d.get("change") is not None and d["change"] <= -3.0:
            alerts.append((name, d["price"], d["change"]))
    if not alerts:
        return
    lines = ["📉 Просадка в твоём портфеле сегодня:\n"]
    for name, price, chg in alerts:
        lines.append("• {} — {:.2f} ₽ ({:.1f}%)".format(name, price, chg))
    lines.append("\nЭто дивидендные акции — не продавай на просадке.")
    lines.append("Дивиденды не зависят от цены, только от отсечки.")
    lines.append("Если хочешь докупить — /rebalance покажет сколько и чего.")
    msg = "\n".join(lines)
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
    md    = fetch_all_market_data()
    lv    = live_portfolio_value(md)
    total = sum(lv.values())
    cost  = sum(p["rub"] for p in PORTFOLIO.values())
    pnl   = total - cost

    bonds  = sum(lv[k] for k, p in PORTFOLIO.items() if p["group"] == "bonds")
    stocks = sum(lv[k] for k, p in PORTFOLIO.items() if p["group"] == "stocks")
    liquid = sum(lv[k] for k, p in PORTFOLIO.items() if p["group"] == "liquid")

    lines = []
    pnl_icon = "📈" if pnl >= 0 else "📉"
    lines.append("💼 Портфель: {}".format(rub(total)))
    lines.append("{} П&L: {}{} ({}{:.1f}%)".format(
        pnl_icon,
        "+" if pnl >= 0 else "", rub(abs(pnl)),
        "+" if pnl >= 0 else "-", abs(pnl / cost * 100) if cost else 0))
    lines.append("🏦 Облигации:   {} ({}%)".format(rub(bonds),  pct(bonds,  total)))
    lines.append("📈 Акции/фонды: {} ({}%)".format(rub(stocks), pct(stocks, total)))
    lines.append("💵 Ликвидность: {} ({}%)".format(rub(liquid), pct(liquid, total)))
    lines.append("")

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

    idx = md.get("index")
    if idx and idx.get("value"):
        lines.append("📊 Индекс МосБиржи: {:,.0f}{}".format(
            idx["value"], chg_str(idx.get("change"))).replace(",", " "))

    st = md.get("stocks", {})
    for ticker, name in [("SBER","Сбер"), ("MTSS","МТС"), ("MOEX","Мосбиржа"), ("TMOS","TMOS"), ("LQDT","LQDT")]:
        d = st.get(ticker)
        if d:
            lines.append("  {} — {:.2f} ₽{}".format(name, d["price"], chg_str(d.get("change"))))

    ofz = md.get("ofz", {})
    ofz_rows = []
    for isin, name in [("SU26246RMFS7","26246"), ("SU26252RMFS5","26252"), ("RU000A0JVW48","26218")]:
        d = ofz.get(isin)
        if d:
            ofz_rows.append("  ОФЗ {} — {:.1f}% ({:.0f} ₽){}".format(
                name, d["price_pct"], d["price_pct"] * 10, chg_str(d.get("change"))))
    if ofz_rows:
        lines.append("🏦 ОФЗ:")
        lines.extend(ofz_rows)
    lines.append("")

    # Upcoming cutoff alerts
    urgent_cutoffs = [a for a in CUTOFF_ALERTS if 0 <= days_until(a["buy_before"]) <= 14]
    if urgent_cutoffs:
        lines.append("⏰ Срочно — дивидендные отсечки:")
        for a in urgent_cutoffs:
            d = days_until(a["buy_before"])
            lines.append("  • {} до {}: {} (через {} дн.)".format(
                a["name"], fmt_date(a["buy_before"]), a["status"], d))
        lines.append("")

    # Top critical news
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

    lines.append("🎯 Действия: /plan  |  Дивиденды: /dividends  |  Новости: /news")
    return "\n".join(lines)

def cmd_evening():
    md = fetch_all_market_data()
    lv    = live_portfolio_value(md)
    total = sum(lv.values())
    cost  = sum(p["rub"] for p in PORTFOLIO.values())
    pnl   = total - cost

    lines = ["🌆 Итоги дня\n"]
    pnl_icon = "📈" if pnl >= 0 else "📉"
    lines.append("{} Портфель: {}  (П&L {}{})".format(
        pnl_icon, rub(total), "+" if pnl >= 0 else "", rub(abs(pnl))))
    lines.append("")

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
    md = fetch_all_market_data()
    lv = live_portfolio_value(md)
    total = sum(lv.values())
    cost  = sum(p["rub"] for p in PORTFOLIO.values())
    pnl   = total - cost

    bonds_v  = sum(lv[k] for k, p in PORTFOLIO.items() if p["group"] == "bonds")
    stocks_v = sum(lv[k] for k, p in PORTFOLIO.items() if p["group"] == "stocks")
    liquid_v = sum(lv[k] for k, p in PORTFOLIO.items() if p["group"] == "liquid")

    st  = md.get("stocks", {})
    ofz = md.get("ofz", {})

    lines = [
        "📊 Портфель Саши",
        "Итого: {}  (П&L {}{})".format(
            rub(total), "+" if pnl >= 0 else "", rub(abs(pnl))),
        "",
    ]

    lines.append("🏦 Облигации — {} ({}%):".format(rub(bonds_v), pct(bonds_v, total)))
    ofz_items = [
        ("ofz_26246", "SU26246RMFS7", "ОФЗ 26246"),
        ("ofz_26252", "SU26252RMFS5", "ОФЗ 26252"),
        ("ofz_26218", "RU000A0JVW48", "ОФЗ 26218"),
    ]
    for key, isin, name in ofz_items:
        pos = PORTFOLIO[key]
        d = ofz.get(isin)
        live = lv[key]
        diff = live - pos["rub"]
        price_str = " | {:.1f}% ({:.0f} ₽){}".format(
            d["price_pct"], d["price_pct"] * 10, chg_str(d.get("change"))) if d else ""
        lines.append("  {} × {} шт — {}  ({}{}){}".format(
            name, pos["units"], rub(live),
            "+" if diff >= 0 else "", rub(abs(diff)), price_str))

    lines.append("")
    lines.append("📈 Акции и фонды — {} ({}%):".format(rub(stocks_v), pct(stocks_v, total)))
    stock_items = [
        ("tmos",   "TMOS", "TMOS"),
        ("sber",   "SBER", "Сбер"),
        ("mts",    "MTSS", "МТС"),
        ("moex_s", "MOEX", "Мосбиржа"),
    ]
    for key, ticker, name in stock_items:
        pos = PORTFOLIO[key]
        d = st.get(ticker)
        live = lv[key]
        diff = live - pos["rub"]
        price_str = " | {:.2f} ₽{}".format(d["price"], chg_str(d.get("change"))) if d else ""
        lines.append("  {} × {} шт — {}  ({}{}){}".format(
            name, pos["units"], rub(live),
            "+" if diff >= 0 else "", rub(abs(diff)), price_str))

    lines.append("")
    lines.append("💵 Ликвидность — {} ({}%):".format(rub(liquid_v), pct(liquid_v, total)))
    lines.append("  Вклад ПСБ — {} (20%, 210д)".format(rub(PORTFOLIO["psb"]["rub"])))
    d = st.get("LQDT")
    lqdt_units = PORTFOLIO["lqdt"]["units"]
    lqdt_str = " × {} шт".format(lqdt_units) if lqdt_units else " (резерв пуст)"
    price_str = " | {:.2f} ₽{}".format(d["price"], chg_str(d.get("change"))) if d else ""
    lines.append("  LQDT{} — {}{}".format(lqdt_str, rub(lv["lqdt"]), price_str))

    lines.append("\nОбновить: /update sber 22000 [шт]  |  План: /plan")
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
            "✅ Изменений в портфеле не требуется.\n"
            "📋 Текущий план: /plan"
        )

    lines = ["📰 Важные новости для портфеля\n"]
    shown_labels = set()
    for i, item in enumerate(news[:5], 1):
        lines.append("{}. {}".format(i, item["label"]))
        lines.append("   {}".format(item["title"]))
        if item.get("date"):
            lines.append("   {}".format(item["date"]))
        if item.get("link"):
            lines.append("   {}".format(item["link"]))
        # Show recommendation once per label type
        label = item["label"]
        if label not in shown_labels and label in NEWS_ACTIONS:
            shown_labels.add(label)
            lines.append("   💡 {}".format(NEWS_ACTIONS[label]))
        lines.append("")

    critical = [n for n in news if n["priority"] == "critical"]
    if critical:
        lines.append("⚠️ {} критических — оцени влияние перед действием.".format(len(critical)))
    else:
        lines.append("✅ Критических событий нет. Изменений не требуется.")

    return "\n".join(lines)

def cmd_income():
    coupon_total = 0.0
    bond_lines = []
    for key in ["ofz_26246", "ofz_26252", "ofz_26218"]:
        pos = PORTFOLIO[key]
        units = pos["units"] or 0
        annual = pos["coupon"] * units * 2  # 2 payments/year
        coupon_total += annual
        bond_lines.append("  {} × {} шт × 2 = {}".format(
            pos["label"], units, rub(annual)))

    psb = PORTFOLIO["psb"]["rub"]
    psb_income = psb * 0.20 * 210 / 365

    # Next 12 months dividends
    today = date.today()
    upcoming_divs = [
        p for p in PAYMENT_CALENDAR
        if p["type"] == "div" and 0 <= (p["date"] - today).days <= 365
    ]
    div_total = sum(p["amount"] for p in upcoming_divs)
    div_lines = []
    for p in sorted(upcoming_divs, key=lambda x: x["date"]):
        div_lines.append("  {} ({}) — {}  [{}]".format(
            p["name"], fmt_date(p["date"]), rub(p["amount"]), p["note"]))

    iis_deduction = min(IIS_CONTRIBUTION, 400000) * 0.13
    tax_coupons   = coupon_total * 0.13
    tax_divs      = div_total * 0.13
    net_coupons   = coupon_total - tax_coupons
    net_divs      = div_total - tax_divs
    net_passive   = psb_income + net_coupons + net_divs

    lines = [
        "💸 Доходы портфеля\n",
        "🏦 Вклад ПСБ (20%, 210 дней):",
        "  Вложено: {}".format(rub(psb)),
        "  Доход за срок: ~{}  (налог не удерживается — ниже порога)\n".format(rub(psb_income)),
        "🏦 Купоны ОФЗ (прогноз на год):",
    ]
    lines.extend(bond_lines)
    lines.append("  Брутто: ~{}  →  Налог 13%: ~{}  →  На руки: ~{}\n".format(
        rub(coupon_total), rub(tax_coupons), rub(net_coupons)))
    lines.append("📊 Дивиденды (ближайшие 12 мес.):")
    if div_lines:
        lines.extend(div_lines)
        lines.append("  Брутто: ~{}  →  Налог 13%: ~{}  →  На руки: ~{}\n".format(
            rub(div_total), rub(tax_divs), rub(net_divs)))
    else:
        lines.append("  —\n")
    lines.append("📈 TMOS (195 шт) — дивидендов не платит:")
    lines.append("  Фонд реинвестирует доход в индекс → рост через цену пая.")
    lines.append("  Доходность отслеживай через /portfolio (П&L)\n")
    lines.append("💰 Чистый пассивный доход (на руки): ~{}".format(rub(net_passive)))
    lines.append("   Брутто: ~{}  →  налог ~{}  →  на руки: ~{}".format(
        rub(psb_income + coupon_total + div_total), rub(tax_coupons + tax_divs), rub(net_passive)))
    lines.append("")
    lines.append("🏛 ИИС (тип не выбран — выберешь при закрытии):")
    lines.append("  Тип А: возврат 13% от взносов ежегодно (до 52 000 ₽/год)")
    lines.append("    → выгоден если вносишь крупные суммы каждый год")
    lines.append("  Тип Б: прибыль от продажи бумаг — без налога при закрытии")
    lines.append("    → выгоден если портфель сильно вырос в цене")
    lines.append("  ⚠️ Дивиденды и купоны — 13% в обоих типах (уже учтено выше)")
    lines.append("  💡 Держи ИИС минимум 3 года — иначе никакой льготы")
    lines.append("")

    # Полный календарь выплат
    today = date.today()
    all_upcoming = sorted([p for p in PAYMENT_CALENDAR if p["date"] >= today], key=lambda x: x["date"])
    all_past = sorted([p for p in PAYMENT_CALENDAR if p["date"] < today], key=lambda x: x["date"])
    lines.append("📅 Календарь выплат\n")
    if all_upcoming:
        for p in all_upcoming:
            d = days_until(p["date"])
            icon = "💰" if p["type"] == "div" else "🏦"
            tag = "дивиденд" if p["type"] == "div" else "купон"
            lines.append("  {} {} {} — {}  (через {} дн.)".format(
                icon, fmt_date(p["date"]), p["name"], rub(p["amount"]), d))
            lines.append("    {} | {}".format(tag, p["note"]))
    year_total = sum(p["amount"] for p in all_upcoming if p["date"].year == today.year)
    lines.append("\n  Итого в {} году: ~{}".format(today.year, rub(year_total)))
    if all_past:
        lines.append("\n✅ Выплачено ранее:")
        for p in all_past:
            icon = "💰" if p["type"] == "div" else "🏦"
            lines.append("  {} {} {} — {}".format(icon, fmt_date(p["date"]), p["name"], rub(p["amount"])))
    return "\n".join(lines)

def cmd_dividends():
    today = date.today()
    lines = ["📅 Календарь выплат\n"]

    upcoming = sorted(
        [p for p in PAYMENT_CALENDAR if p["date"] >= today],
        key=lambda x: x["date"]
    )
    past = sorted(
        [p for p in PAYMENT_CALENDAR if p["date"] < today],
        key=lambda x: x["date"]
    )

    if upcoming:
        lines.append("⏭ Предстоящие:")
        for p in upcoming:
            d = days_until(p["date"])
            icon = "💰" if p["type"] == "div" else "🏦"
            tag = "дивиденд" if p["type"] == "div" else "купон"
            lines.append("  {} {} {}  — {}  (через {} дн.)".format(
                icon, fmt_date(p["date"]), p["name"], rub(p["amount"]), d))
            lines.append("    {} | {}".format(tag, p["note"]))
        lines.append("")

    total_upcoming = sum(p["amount"] for p in upcoming if p["date"].year == today.year)
    lines.append("💵 Итого выплат в {} году: ~{}".format(today.year, rub(total_upcoming)))

    if past:
        lines.append("\n✅ Выплачено ранее:")
        for p in past:
            icon = "💰" if p["type"] == "div" else "🏦"
            lines.append("  {} {} {}  — {}".format(icon, fmt_date(p["date"]), p["name"], rub(p["amount"])))

    lines.append("\nОтсечки: /plan")
    return "\n".join(lines)

def cmd_plan():
    today = date.today()
    lines = ["🎯 План действий\n"]

    # Срочные задачи (с дедлайном) — показываем только актуальные (не старше 30 дней)
    urgent = [t for t in TODO_ITEMS
              if t["deadline"] is not None and days_until(t["deadline"]) >= -30]
    if urgent:
        lines.append("🚨 СРОЧНО:")
        for t in sorted(urgent, key=lambda x: x["deadline"]):
            d = days_until(t["deadline"])
            if d >= 0:
                lines.append("  • {} (осталось {} дн.)".format(t["action"], d))
            else:
                lines.append("  • {} (просрочено {} дн. назад — выполни или обнови план)".format(
                    t["action"], abs(d)))
        lines.append("")

    # Плановые задачи
    planned = [t for t in TODO_ITEMS if t["deadline"] is None]
    if planned:
        lines.append("📋 Плановые покупки:")
        for t in sorted(planned, key=lambda x: x["priority"]):
            lines.append("  {}. {}".format(t["priority"], t["action"]))
        total_needed = sum(t["amount"] for t in planned)
        lines.append("  Итого нужно: ~{}".format(rub(total_needed)))
        lines.append("")

    # Отсечки
    lines.append("📅 Дивидендные отсечки:")
    for a in CUTOFF_ALERTS:
        d = days_until(a["buy_before"])
        if d >= 0:
            status_time = "через {} дн.".format(d)
        else:
            status_time = "отсечка прошла"
        lines.append("  • {} — последний день {} ({})".format(
            a["name"], fmt_date(a["buy_before"]), status_time))
        lines.append("    {}".format(a["status"]))
    lines.append("")

    # Ближайшие выплаты
    upcoming = sorted(
        [p for p in PAYMENT_CALENDAR if p["date"] >= today][:3],
        key=lambda x: x["date"]
    )
    if upcoming:
        lines.append("💰 Ближайшие выплаты:")
        for p in upcoming:
            icon = "💰" if p["type"] == "div" else "🏦"
            lines.append("  {} {} {} — {}".format(
                icon, fmt_date(p["date"]), p["name"], rub(p["amount"])))
        lines.append("")

    lines.append("📜 Стратегия:\n"
                 "  Новые деньги: 50% ОФЗ · 30% TMOS · 20% LQDT\n"
                 "  ОФЗ 26218 не докупать сверх +2 шт по плану")
    lines.append("")

    # Ребалансировка (вставлена из /rebalance)
    md    = fetch_all_market_data()
    lv    = live_portfolio_value(md)
    total_live = sum(lv.values())
    bonds_v  = sum(lv[k] for k, p in PORTFOLIO.items() if p["group"] == "bonds")
    stocks_v = sum(lv[k] for k, p in PORTFOLIO.items() if p["group"] == "stocks")
    liquid_v = sum(lv[k] for k, p in PORTFOLIO.items() if p["group"] == "liquid")
    diff_b = total_live * TARGET_ALLOCATION["bonds"]  / 100 - bonds_v
    diff_s = total_live * TARGET_ALLOCATION["stocks"] / 100 - stocks_v
    diff_l = total_live * TARGET_ALLOCATION["liquid"] / 100 - liquid_v

    def _arrow(diff):
        if diff > 500:   return "↑ +{}".format(rub(diff))
        if diff < -500:  return "↓ перевес"
        return "✅ ок"

    lines.append("⚖️ Баланс сейчас (цель 40/35/25%):")
    lines.append("  Облигации:   {:.1f}%  {}".format(pct(bonds_v,  total_live), _arrow(diff_b)))
    lines.append("  Акции/фонды: {:.1f}%  {}".format(pct(stocks_v, total_live), _arrow(diff_s)))
    lines.append("  Ликвидность: {:.1f}%  {}".format(pct(liquid_v, total_live), _arrow(diff_l)))
    return "\n".join(lines)

def cmd_rebalance():
    md    = fetch_all_market_data()
    lv    = live_portfolio_value(md)
    total = sum(lv.values())

    bonds_v  = sum(lv[k] for k, p in PORTFOLIO.items() if p["group"] == "bonds")
    stocks_v = sum(lv[k] for k, p in PORTFOLIO.items() if p["group"] == "stocks")
    liquid_v = sum(lv[k] for k, p in PORTFOLIO.items() if p["group"] == "liquid")

    target_b = total * TARGET_ALLOCATION["bonds"]  / 100
    target_s = total * TARGET_ALLOCATION["stocks"] / 100
    target_l = total * TARGET_ALLOCATION["liquid"] / 100

    diff_b = target_b - bonds_v
    diff_s = target_s - stocks_v
    diff_l = target_l - liquid_v

    def arrow(diff):
        if diff > 500:
            return "↑ купить ~{}".format(rub(diff))
        if diff < -500:
            return "↓ перевес ~{}".format(rub(abs(diff)))
        return "✅ в балансе"

    lines = [
        "⚖️ Ребалансировка портфеля\n",
        "Портфель: {}  |  Цель задана стратегией\n".format(rub(total)),
        "                  Сейчас    Цель    Действие",
        "🏦 Облигации:   {: >5.1f}%  → {}%  {}".format(
            pct(bonds_v, total),  TARGET_ALLOCATION["bonds"],  arrow(diff_b)),
        "📈 Акции/фонды: {: >5.1f}%  → {}%  {}".format(
            pct(stocks_v, total), TARGET_ALLOCATION["stocks"], arrow(diff_s)),
        "💵 Ликвидность: {: >5.1f}%  → {}%  {}".format(
            pct(liquid_v, total), TARGET_ALLOCATION["liquid"], arrow(diff_l)),
        "",
    ]

    # Specific buy suggestions
    suggestions = []
    if diff_b > 500:
        suggestions.append("  🏦 ОФЗ 26246 или 26252 на ~{}".format(rub(diff_b)))
    if diff_s > 500:
        suggestions.append("  📈 TMOS на ~{}".format(rub(diff_s)))
    if diff_l > 500:
        suggestions.append("  💵 LQDT на ~{}".format(rub(diff_l)))

    if suggestions:
        lines.append("Что купить для баланса:")
        lines.extend(suggestions)
        lines.append("")

    # Current state details
    st  = md.get("stocks", {})
    ofz = md.get("ofz", {})
    lines.append("Детально сейчас:")
    for key, isin, name in [("ofz_26246","SU26246RMFS7","ОФЗ 26246"),
                              ("ofz_26252","SU26252RMFS5","ОФЗ 26252"),
                              ("ofz_26218","RU000A0JVW48","ОФЗ 26218")]:
        lines.append("  {} — {}".format(name, rub(lv[key])))
    for key, ticker, name in [("tmos","TMOS","TMOS"),("sber","SBER","Сбер"),
                                ("mts","MTSS","МТС"),("moex_s","MOEX","Мосбиржа")]:
        d = st.get(ticker)
        price_str = " ({:.2f} ₽)".format(d["price"]) if d else ""
        lines.append("  {}{} — {}".format(name, price_str, rub(lv[key])))
    lines.append("  Вклад ПСБ — {}".format(rub(lv["psb"])))
    lines.append("  LQDT — {}".format(rub(lv["lqdt"])))
    lines.append("")
    lines.append("Пополнить на сумму: /addmoney 3000")
    return "\n".join(lines)

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
            "ОФЗ 26218 — не более +2 шт по плану."
        ).format(rub(amount), rub(b), rub(t), rub(l))
    except:
        return "Пример: /addmoney 50000"

def cmd_update(args):
    global IIS_CONTRIBUTION
    parts = args.strip().split()
    if len(parts) < 2:
        return (
            "Формат: /update ПОЗИЦИЯ СУММА [ШТ]\n\n"
            "Примеры:\n"
            "/update sber 22000\n"
            "/update sber 22000 68\n"
            "/update 26246 27000 31\n"
            "/update tmos 28000\n"
            "/update lqdt 18000 8303\n"
            "/update psb 55000\n"
            "/update iis 150000  ← взносы в ИИС для вычета"
        )
    key = UPDATE_ALIASES.get(parts[0].lower())
    if not key:
        return "Не нашла позицию '{}'. Пример: /update sber 22000".format(parts[0])
    if key == "iis":
        try:
            amount = int(parts[1].replace(",", ""))
            if amount < 0:
                raise ValueError
            IIS_CONTRIBUTION = amount
            save_portfolio()
            return "✅ Взносы в ИИС: {}\nСохранено.\nДетали: /income".format(rub(amount))
        except:
            return "Не понял сумму. Пример: /update iis 150000"
    try:
        amount = int(parts[1].replace(",", ""))
        if amount < 0:
            raise ValueError
    except:
        return "Не понял сумму. Пример: /update sber 22000"

    old_rub   = PORTFOLIO[key]["rub"]
    old_units = PORTFOLIO[key].get("units")
    PORTFOLIO[key]["rub"] = amount

    units_msg = ""
    if len(parts) >= 3:
        try:
            new_units = int(parts[2])
            PORTFOLIO[key]["units"] = new_units
            units_msg = "\nКоличество: {} → {} шт".format(old_units, new_units)
        except:
            pass

    diff  = amount - old_rub
    total = sum(p["rub"] for p in PORTFOLIO.values())
    save_portfolio()
    return "✅ {} → {}{}\nИзменение: {}{}\nПортфель: {}\nСохранено.".format(
        PORTFOLIO[key]["label"], rub(amount), units_msg,
        "+" if diff >= 0 else "", rub(abs(diff)), rub(total))

def cmd_subscribe(chat_id):
    subscribed_chats.add(chat_id)
    save_subscriptions()
    return (
        "✅ Подписка активирована!\n\n"
        "Буду присылать:\n"
        "☀️ 9:00 МСК — утренний обзор с П&L\n"
        "🌆 19:00 МСК — итоги дня\n"
        "🚨 В любое время — критические события\n"
        "   (решение ЦБ, дивиденды Сбера/МТС/Мосбиржи)\n"
        "⏰ За 7 дней — напоминание об отсечках дивидендов\n"
        "💰 За 3 дня — напоминание о выплатах\n"
        "📉 Вечером — alert при падении акций >3%\n\n"
        "Подписка сохранена — работает после перезапуска.\n"
        "Отключить: /unsubscribe"
    )

def cmd_unsubscribe(chat_id):
    subscribed_chats.discard(chat_id)
    save_subscriptions()
    return "🔕 Оповещения отключены. Включить: /subscribe"

def cmd_rules():
    return (
        "📜 Правила Саши\n\n"
        "1. Действовать только по плану.\n"
        "2. Новые деньги: 50% ОФЗ · 30% TMOS · 20% LQDT.\n"
        "3. ОФЗ 26218 — не докупать сверх +2 шт по плану.\n"
        "4. Акции не наращивать сверх стратегии.\n"
        "5. Проверять портфель раз в месяц.\n"
        "6. Не принимать решений на эмоциях.\n"
        "7. Цель: долгосрочный рост с контролем риска.\n"
        "8. ИИС даёт налоговый вычет — держать минимум 3 года."
    )

def cmd_help():
    return (
        "🤖 Family Office Саши v4\n\n"
        "/morning — утренний обзор: П&L, ставка, курс, рынок\n"
        "/evening — итоги дня: П&L и важные события\n"
        "/portfolio — портфель с живыми ценами и П&L\n"
        "/news — важные новости + что именно делать\n"
        "/plan — что купить, отсечки, баланс портфеля\n"
        "/income — доходы, календарь выплат, ИИС\n"
        "/addmoney 3000 — как распределить новые деньги\n"
        "/update ПОЗИЦИЯ СУММА [ШТ] — обновить позицию\n"
        "/subscribe — авто: 9:00, 19:00, срочные события\n"
        "/unsubscribe — отключить\n"
        "/rules — правила инвестирования\n"
        "/help — эта справка"
    )

# ─── Router ───────────────────────────────────────────────────────────────────

def answer(text, chat_id):
    t = text.strip()
    if t == "/start":
        subscribed_chats.add(chat_id)
        save_subscriptions()
        return cmd_help() + "\n\n✅ Уведомления включены автоматически.\nОтключить: /unsubscribe"
    if t == "/help":                            return cmd_help()
    if t == "/morning":                         return cmd_morning()
    if t == "/evening":                         return cmd_evening()
    if t == "/portfolio":                       return cmd_portfolio()
    if t in ("/news", "/market", "/alert"):     return cmd_news()
    if t == "/income":                          return cmd_income()
    if t == "/dividends":                       return cmd_income()   # объединено с /income
    if t == "/plan":                            return cmd_plan()
    if t == "/rebalance":                       return cmd_plan()     # объединено с /plan
    if t == "/rules":                           return cmd_rules()
    if t == "/subscribe":                       return cmd_subscribe(chat_id)
    if t == "/unsubscribe":                     return cmd_unsubscribe(chat_id)
    if t.startswith("/addmoney"):
        parts = t.split(maxsplit=1)
        return cmd_addmoney(parts[1] if len(parts) > 1 else "")
    if t.startswith("/update"):
        parts = t.split(maxsplit=1)
        return cmd_update(parts[1] if len(parts) > 1 else "")
    # Legacy aliases
    if t in ("/dashboard", "/today", "/action"): return cmd_morning()
    if t in ("/advice", "/signal", "/watch", "/priority"): return cmd_news()
    if t in ("/meeting",):                      return cmd_portfolio()
    if t in ("/year", "/psb"):                  return cmd_income()
    return "Команда не найдена. Напиши /help"

# ─── Main loop ────────────────────────────────────────────────────────────────

load_state()
print("SashaInvestBot v4.2 started — {} subscriptions loaded".format(len(subscribed_chats)))

while True:
    try:
        if not BOT_TOKEN:
            print("BOT_TOKEN missing")
            time.sleep(10)
            continue

        check_and_push_news()
        check_cutoff_alerts()
        check_payment_reminders()
        check_price_drops()
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
