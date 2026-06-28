import os
import time
import requests
import xml.etree.ElementTree as ET
from html import unescape

BOT_TOKEN = os.environ.get("BOT_TOKEN")
last_update_id = 0

portfolio = {
    "psb": 50000,
    "ofz_26246": 25230,
    "ofz_26252": 10208,
    "ofz_26218": 34830,
    "tmos": 24998,
    "sber": 19856,
    "mts": 8680,
    "moex": 9591,
    "lqdt": 16607
}

RSS_SOURCES = [
    ("Банк России — пресс-релизы", "https://www.cbr.ru/rss/RssPress"),
    ("Банк России — новости", "https://www.cbr.ru/rss/eventrss"),
    ("Московская биржа — новости", "https://www.moex.com/export/news.aspx?cat=101"),
    ("Московская биржа — итоги торгов", "https://www.moex.com/export/news.aspx?cat=102")
]


def rub(x):
    return str(int(x)).replace(",", " ") + " ₽"


def pct(value, total):
    return round(value / total * 100, 1)


def totals():
    bonds = portfolio["ofz_26246"] + portfolio["ofz_26252"] + portfolio["ofz_26218"]
    stocks = portfolio["tmos"] + portfolio["sber"] + portfolio["mts"] + portfolio["moex"]
    liquidity = portfolio["psb"] + portfolio["lqdt"]
    total = bonds + stocks + liquidity
    return total, bonds, stocks, liquidity


def clean_text(text):
    if not text:
        return ""
    text = unescape(text)
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def fetch_rss_items(url, limit=5):
    try:
        headers = {"User-Agent": "SashaInvestBot/1.0"}
        response = requests.get(url, headers=headers, timeout=12)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        items = []
        for item in root.findall(".//item")[:limit]:
            title = clean_text(item.findtext("title"))
            link = clean_text(item.findtext("link"))
            date = clean_text(item.findtext("pubDate"))
            if title:
                items.append({"title": title, "link": link, "date": date})
        return items
    except Exception as e:
        print("RSS error:", e)
        return []


def classify_news(title):
    t = title.lower()

    if any(w in t for w in ["ключев", "ставк", "инфляц", "банк россии", "цб"]):
        return "ставка"

    if any(w in t for w in ["офз", "облигац", "доходност"]):
        return "облигации"

    if any(w in t for w in ["дивиденд", "сбер", "мтс", "московск", "moex"]):
        return "дивиденды"

    if any(w in t for w in ["индекс", "торгов", "рынок"]):
        return "рынок"

    return "общее"


def impact(category):
    if category == "ставка":
        return "Влияние: высокое. Важно для ОФЗ, LQDT и вклада."
    if category == "облигации":
        return "Влияние: высокое. Важно для ОФЗ и новых покупок облигаций."
    if category == "дивиденды":
        return "Влияние: среднее/высокое. Важно для Сбера, МТС, Мосбиржи и TMOS."
    if category == "рынок":
        return "Влияние: среднее. Важно для TMOS и отдельных акций."
    return "Влияние: низкое/среднее. Общий рыночный фон."


def market_report():
    news = []

    for source, url in RSS_SOURCES:
        for item in fetch_rss_items(url):
            category = classify_news(item["title"])
            if category != "общее":
                news.append({
                    "source": source,
                    "title": item["title"],
                    "date": item["date"],
                    "link": item["link"],
                    "category": category
                })

    if not news:
        return """
📰 Рыночный обзор

Свежих важных новостей по проверенным источникам не найдено.

Источники:
• Банк России
• Московская биржа

Решение:
изменений в портфеле не требуется.
"""

    text = "📰 Рыночный обзор для портфеля Саши\n\n"
    text += "Источники: Банк России, Московская биржа.\n\n"

    for i, item in enumerate(news[:5], start=1):
        text += str(i) + ". " + item["title"] + "\n"
        text += "Источник: " + item["source"] + "\n"
        if item["date"]:
            text += "Дата: " + item["date"] + "\n"
        text += impact(item["category"]) + "\n"
        if item["link"]:
            text += "Ссылка: " + item["link"] + "\n"
        text += "\n"

    text += """
Заключение:
ОФЗ — держать.
TMOS — докупать планово.
LQDT — резерв.
Отдельные акции — не увеличивать сверх стратегии.

Если нет новости про ставку, дивиденды или резкое движение рынка — изменений не требуется.
"""
    return text


def send_message(chat_id, text):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"

    if len(text) <= 3900:
        requests.post(url, data={"chat_id": chat_id, "text": text})
    else:
        while text:
            part = text[:3900]
            text = text[3900:]
            requests.post(url, data={"chat_id": chat_id, "text": part})
            time.sleep(0.5)


def answer_for(text):
    total, bonds, stocks, liquidity = totals()

    if text == "/help":
        return """
🤖 Family Office Саши

Команды:
/portfolio - структура портфеля
/dashboard - главный экран
/market - свежие новости из интернета
/alert - важные сигналы
/priority - приоритеты
/morning - утренний обзор
/watch - что контролировать
/action - решение на сегодня
/year - прогноз до конца года
/rebalance - ребалансировка
/addmoney 50000 - распределить новую сумму
/income - примерный доход
/meeting - инвестиционный обзор
/advice - точное заключение
/signal - действия по портфелю
/psb - вклад ПСБ
/rules - правила инвестирования
/today - краткий отчёт
/help - список команд
"""

    if text == "/portfolio":
        return """
📊 Портфель Саши

Общая сумма: {}

🏦 Облигации: {} / {}%
📈 Акции и фонды: {} / {}%
💵 Ликвидность: {} / {}%

Оценка:
умеренно-консервативный портфель.
""".format(rub(total), rub(bonds), pct(bonds, total), rub(stocks), pct(stocks, total), rub(liquidity), pct(liquidity, total))

    if text == "/dashboard":
        return """
📊 Family Office Саши

Портфель: {}
Стратегия: умеренно-консервативная
Риск: средний-низкий

Структура:
🏦 Облигации: {}%
📈 Акции и фонды: {}%
💵 Ликвидность: {}%

Статус:
портфель соответствует стратегии.

Следующее пополнение:
🏦 ОФЗ — 50%
📈 TMOS — 30%
💵 LQDT — 20%
""".format(rub(total), pct(bonds, total), pct(stocks, total), pct(liquidity, total))

    if text == "/market":
        return market_report()

    if text == "/alert":
        report = market_report()

        if "Свежих важных новостей" in report:
            return """
🔔 Активные сигналы

Существенных событий по проверенным источникам не найдено.

Статус:
изменений в портфеле не требуется.

Контроль:
• ставка ЦБ;
• доходности ОФЗ;
• дивиденды Сбера, МТС и Мосбиржи;
• важные новости российского рынка.
"""

        return """
🔔 Сигнал

Найдены важные события в проверенных источниках.

Детали:
напиши /market

Базовое решение:
сначала проверить влияние новости, затем принимать решение по позициям.
"""

    if text == "/priority":
        return """
🎯 Приоритеты портфеля

1. Текущие позиции — держать.

2. Новые средства:
🏦 ОФЗ — 50%
📈 TMOS — 30%
💵 LQDT — 20%

3. ОФЗ 26218 — не увеличивать.

4. Отдельные акции не наращивать сверх текущей стратегии.

Срочных действий нет.
"""

    if text == "/morning":
        return """
🌅 Утренний обзор Саши

Портфель: {}

Структура:
🏦 Облигации: {}%
📈 Акции и фонды: {}%
💵 Ликвидность: {}%

Рынок:
для актуальных новостей напиши /market

Действия:
• покупок не требуется;
• продаж не требуется;
• новые средства распределять по плану.
""".format(rub(total), pct(bonds, total), pct(stocks, total), pct(liquidity, total))

    if text == "/watch":
        return """
🔔 Что контролировать

1. Ключевая ставка ЦБ.
2. Доходности ОФЗ.
3. Инфляция.
4. Дивиденды Сбера.
5. Дивиденды МТС.
6. Новости Московской биржи.
7. Индекс МосБиржи.
8. Состояние российского рынка.

Главная команда:
для свежей проверки напиши /market
"""

    if text == "/action":
        return """
🎯 Решение на сегодня

Покупать: нет
Продавать: нет
Ребалансировка: не требуется

Если появились новые деньги:
🏦 ОФЗ — 50%
📈 TMOS — 30%
💵 LQDT — 20%

Текущие позиции:
держать.
"""

    if text == "/year":
        psb_income = portfolio["psb"] * 0.20 * 210 / 365
        bond_income = (
            portfolio["ofz_26246"] * 0.12 +
            portfolio["ofz_26252"] * 0.125 +
            portfolio["ofz_26218"] * 0.085
        )

        return """
📅 Прогноз дохода

ПСБ вклад за 210 дней: {}
ОФЗ купоны за год: {}

Итого по вкладу и купонам:
примерно {}

Важно:
без учёта налогов, изменения цен облигаций, дивидендов и результата акций.
""".format(rub(psb_income), rub(bond_income), rub(psb_income + bond_income))

    if text == "/rebalance":
        return """
⚖️ Ребалансировка

Целевая логика новых пополнений:
50% — облигации
30% — TMOS
20% — LQDT

Изменений по текущим позициям не требуется.
"""

    if text.startswith("/addmoney"):
        parts = text.split()

        if len(parts) < 2:
            return "Формат: /addmoney 50000"

        try:
            amount = int(parts[1])
            bonds_add = int(amount * 0.50)
            tmos_add = int(amount * 0.30)
            lqdt_add = amount - bonds_add - tmos_add

            return """
💰 Новые деньги: {}

Распределение:
🏦 ОФЗ / облигации: {}
📈 TMOS: {}
💵 LQDT: {}

Заключение:
распределение соответствует умеренно-консервативной стратегии.
""".format(rub(amount), rub(bonds_add), rub(tmos_add), rub(lqdt_add))

        except:
            return "Не понял сумму. Формат: /addmoney 50000"

    if text == "/income":
        psb_income = portfolio["psb"] * 0.20 * 210 / 365
        bond_income = (
            portfolio["ofz_26246"] * 0.12 +
            portfolio["ofz_26252"] * 0.125 +
            portfolio["ofz_26218"] * 0.085
        )

        return """
💸 Примерный доход

ПСБ вклад за 210 дней: {}
ОФЗ купоны за год: {}

Примечание:
расчёт приблизительный, без налогов, изменения цен и реинвестирования.
""".format(rub(psb_income), rub(bond_income))

    if text == "/meeting":
        return """
👩‍💼 Инвестиционный обзор

Стоимость портфеля: {}

Структура:
Облигации: {}%
Акции и фонды: {}%
Ликвидность: {}%

Оценка:
портфель соответствует умеренно-консервативному профилю.

Решение:
текущие позиции держать.
Новые средства направлять в ОФЗ, TMOS и LQDT.
""".format(rub(total), pct(bonds, total), pct(stocks, total), pct(liquidity, total))

    if text == "/advice":
        return """
👩‍💼 Инвестиционное заключение

Портфель: {}
Профиль: умеренно-консервативный
Риск: средний-низкий

Решения по позициям:
ОФЗ 26246 — держать.
ОФЗ 26252 — держать.
ОФЗ 26218 — держать, не докупать.
TMOS — планово докупать.
Сбер — держать.
МТС — держать, долю не увеличивать.
Московская биржа — держать.
LQDT — держать как резерв.

Новые средства:
50% — ОФЗ
30% — TMOS
20% — LQDT

Требуемые действия:
изменений в структуре портфеля сейчас не требуется.
""".format(rub(total))

    if text == "/signal":
        return """
📋 Сигналы по портфелю

Покупать планово:
• новые ОФЗ с привлекательной доходностью;
• TMOS.

Держать:
• ОФЗ 26246
• ОФЗ 26252
• Сбер
• МТС
• Московская биржа
• LQDT

Не увеличивать:
• ОФЗ 26218
• отдельные акции сверх текущей стратегии

Следующее действие:
использовать новые пополнения для ОФЗ, TMOS и LQDT.
"""

    if text == "/psb":
        return """
🏦 Вклад ПСБ

Сумма: 50 000 ₽
Срок: 210 дней
Ставка: 20%

Примерный доход:
около 5 753 ₽ до налогов.

Решение:
держать до окончания срока.
"""

    if text == "/rules":
        return """
📜 Инвестиционные правила

1. Действия только по плану.
2. Новые средства распределяются по структуре: ОФЗ / TMOS / LQDT.
3. Отдельные акции не увеличиваются сверх стратегии.
4. Проверка портфеля — раз в месяц.
5. Основная цель — долгосрочный рост капитала с контролем риска.
"""

    if text == "/today":
        return """
🌅 Отчёт на сегодня

Статус:
портфель соответствует стратегии.

Действия:
• покупок не требуется;
• продаж не требуется;
• ребалансировка не требуется.

Приоритет:
новые средства распределять по плану.
"""

    return "Команда не найдена. Напиши /help"


print("Bot started")

while True:
    try:
        if not BOT_TOKEN:
            print("BOT_TOKEN is missing")
            time.sleep(10)
            continue

        url = "https://api.telegram.org/bot" + BOT_TOKEN + "/getUpdates?offset=" + str(last_update_id + 1)
        updates = requests.get(url, timeout=30).json()

        if updates.get("ok"):
            for update in updates.get("result", []):
                last_update_id = update["update_id"]

                message = update.get("message")
                if not message:
                    continue

                chat_id = message["chat"]["id"]
                text = message.get("text", "")

                send_message(chat_id, answer_for(text))

    except Exception as e:
        print("Error:", e)

    time.sleep(2)
