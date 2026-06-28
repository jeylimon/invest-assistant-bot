import os
import requests
import time
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
    ("Московская биржа — главные новости", "https://moex.com/export/news.aspx?cat=101"),
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
        headers = {
            "User-Agent": "SashaInvestBot/1.0"
        }
        response = requests.get(url, headers=headers, timeout=12)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        items = []

        for item in root.findall(".//item")[:limit]:
            title = clean_text(item.findtext("title"))
            link = clean_text(item.findtext("link"))
            pub_date = clean_text(item.findtext("pubDate"))

            if title:
                items.append({
                    "title": title,
                    "link": link,
                    "date": pub_date
                })

        return items

    except Exception as e:
        print("RSS error:", url, e)
        return []


def classify_news(title):
    t = title.lower()

    if any(word in t for word in ["ключев", "ставк", "денежно-кредит", "инфляц", "цб", "банк россии"]):
        return "ставка/инфляция"

    if any(word in t for word in ["офз", "облигац", "долгов", "доходност"]):
        return "облигации"

    if any(word in t for word in ["дивиденд", "сбер", "мтс", "московск", "moex", "акци"]):
        return "акции/дивиденды"

    if any(word in t for word in ["итоги торгов", "индекс", "рынок акций"]):
        return "рынок"

    return "общее"


def portfolio_impact(category):
    if category == "ставка/инфляция":
        return (
            "Влияние: высокое.\n"
            "Для портфеля: ОФЗ, LQDT и вклад зависят от ставок. "
            "При снижении ставок длинные ОФЗ обычно выглядят лучше, доходность LQDT и новых вкладов со временем снижается."
        )

    if category == "облигации":
        return (
            "Влияние: высокое.\n"
            "Для портфеля: напрямую влияет на ОФЗ 26246, 26252, 26218 и новые покупки облигаций."
        )

    if category == "акции/дивиденды":
        return (
            "Влияние: среднее/высокое.\n"
            "Для портфеля: важно для Сбера, МТС, Московской биржи и TMOS."
        )

    if category == "рынок":
        return (
            "Влияние: среднее.\n"
            "Для портфеля: влияет на TMOS и отдельные акции."
        )

    return (
        "Влияние: низкое/среднее.\n"
        "Для портфеля: учитывать как общий рыночный фон."
    )


def generate_market_report():
    important = []

    for source_name, url in RSS_SOURCES:
        items = fetch_rss_items(url, limit=5)

        for item in items:
            category = classify_news(item["title"])

            if category in ["ставка/инфляция", "облигации", "акции/дивиденды", "рынок"]:
                important.append({
                    "source": source_name,
                    "title": item["title"],
                    "date": item["date"],
                    "link": item["link"],
                    "category": category
                })

    if not important:
        return """
📰 Рыночный обзор

Свежих важных новостей по проверенным источникам не найдено.

Проверенные источники:
• Банк России
• Московская биржа

Рекомендация:
изменений в портфеле не требуется.
"""

    report = "📰 Рыночный обзор для портфеля Саши\n\n"
    report += "Источники: Банк России, Московская биржа.\n\n"

    for i, item in enumerate(important[:5], start=1):
        report += "{}. {}\n".format(i, item["title"])
        report += "Источник: {}\n".format(item["source"])
        if item["date"]:
            report += "Дата: {}\n".format(item["date"])
        report += "{}\n".format(portfolio_impact(item["category"]))
        if item["link"]:
            report += "Ссылка: {}\n".format(item["link"])
        report += "\n"

    report += """
Итоговое заключение:

ОФЗ 26246 — держать.
ОФЗ 26252 — держать.
ОФЗ 26218 — держать, новые деньги туда не направлять.
TMOS — докупать планово.
Сбер — держать.
МТС — держать, долю не увеличивать.
Московская биржа — держать.
LQDT — резерв, не разгонять долю сверх плана.

Требуемые действия:
если нет новости про ставку, дивиденды или резкое движение рынка — изменений не требуется.
"""
    return report


def send_message(chat_id, text):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"

    if len(text) <= 3900:
        requests.post(url, data={"chat_id": chat_id, "text": text})
        return

    parts = []
    while text:
        parts.append(text[:3900])
        text = text[3900:]

    for part in parts:
        requests.post(url, data={"chat_id": chat_id, "text": part})
        time.sleep(0.5)


def answer_for(text):
    total, bonds, stocks, liquidity = totals()

    if text == "/help":
        return """
🤖 Family Office Саши

Команды:
/portfolio - структура портфеля
/rebalance - ребалансировка
/addmoney 50000 - распределить новую сумму
/income - примерный доход
/meeting - инвестиционный обзор
/market - свежие новости из интернета
/advice - точное заключение
/signal - действия по портфелю
/psb - вклад ПСБ
/rules - правила инвестирования
/today - краткий отчёт
/dashboard - главный экран
/alert - важные сигналы
/priority - приоритеты
/morning - утренний обзор
/watch - что контролировать
/action - решение на сегодня
/year - прогноз до конца года
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
""".format(
            rub(total),
            rub(bonds), pct(bonds, total),
            rub(stocks), pct(stocks, total),
            rub(liquidity), pct(liquidity, total)
        )

    if text == "/market":
        return generate_market_report()

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

    

    if text == "/dashboard":
        total, bonds, stocks, liquidity = totals()

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
🟢 Портфель соответствует стратегии.

Следующее пополнение:
🏦 ОФЗ — 50%
📈 TMOS — 30%
💵 LQDT — 20%
""".format(
            rub(total),
            pct(bonds, total),
            pct(stocks, total),
            pct(liquidity, total)
        )

    if text == "/alert":
        return """
🔔 Активные сигналы

Сейчас существенных событий не обнаружено.

Следить за:
• решение Банка России по ставке;
• доходности ОФЗ;
• дивиденды Сбера, МТС и Московской биржи;
• важные новости российского рынка.

Для деталей:
напиши /market
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
    total, bonds, stocks, liquidity = totals()

    return """
🌅 Доброе утро, Саша

💰 Портфель: {}

📊 Структура:
🏦 Облигации: {}%
📈 Акции и фонды: {}%
💵 Ликвидность: {}%

🎯 План:
✅ Ничего не продавать
✅ Новые деньги направлять в ОФЗ и TMOS
✅ LQDT держать как резерв

📌 Главное правило:
не принимать эмоциональных решений.
""".format(
        rub(total),
        pct(bonds, total),
        pct(stocks, total),
        pct(liquidity, total)
    )
    if text == "/watch":
    return """
🔔 Контрольный список

🟢 Ключевая ставка ЦБ
🟢 Доходности ОФЗ
🟢 Индекс МосБиржи
🟢 Дивиденды Сбера
🟢 Дивиденды МТС
🟢 Новости Московской биржи
🟢 Инфляция

Следить ежедневно не нужно.
Проверка достаточно 1 раз в день.
"""
    if text == "/action":
    return """
🎯 Решение на сегодня

Покупать: нет
Продавать: нет
Пополнять: можно

Если появились новые деньги:

🏦 ОФЗ — 50%
📈 TMOS — 30%
💵 LQDT — 20%

Срочных действий нет.
"""
    if text == "/year":
    return """
📅 Прогноз до конца года

🏦 ПСБ вклад:
доход около 5 700 ₽

🏦 Купоны ОФЗ:
около 8 000–9 000 ₽

📈 Потенциал TMOS:
зависит от рынка и не гарантирован.

🎯 Базовый сценарий:
капитал постепенно растёт,
основной доход дают вклад и облигации.
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
