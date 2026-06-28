import os
import requests
import time

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

def send_message(chat_id, text):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text})

def answer_for(text):
    total, bonds, stocks, liquidity = totals()

    if text == "/help":
        return """
🤖 Инвестиционный помощник Саши v3.0

Команды:
/portfolio - портфель
/rebalance - ребалансировка
/addmoney 50000 - распределить новую сумму
/income - примерный доход
/meeting - встреча с консультантом
/psb - вклад ПСБ
/rules - правила инвестирования
/today - отчёт на сегодня
/news - что отслеживать
/help - список команд
"""

    if text == "/portfolio":
        return """
📊 Портфель Саши

Общая сумма: {}

🏦 Облигации: {} / {}%
📈 Акции и фонды: {} / {}%
💵 Ликвидность: {} / {}%

Вывод:
портфель умеренно-консервативный.
""".format(rub(total), rub(bonds), pct(bonds, total), rub(stocks), pct(stocks, total), rub(liquidity), pct(liquidity, total))

    if text == "/rebalance":
        return """
⚖️ Ребалансировка

✅ ОФЗ 26246 — держать
✅ ОФЗ 26252 — держать
⚠️ ОФЗ 26218 — держать, но не докупать
✅ TMOS — можно докупать постепенно
✅ Сбербанк — держать
⚠️ МТС — держать, но не увеличивать долю
✅ Московская биржа — держать
✅ LQDT — оставить как резерв

Новые деньги:
50% — облигации
30% — TMOS
20% — LQDT
"""

    if text.startswith("/addmoney"):
        parts = text.split()
        if len(parts) < 2:
            return "Напиши сумму так: /addmoney 50000"
        try:
            amount = int(parts[1])
            bonds_add = int(amount * 0.50)
            tmos_add = int(amount * 0.30)
            lqdt_add = amount - bonds_add - tmos_add
            return """
💰 Новые деньги: {}

🏦 Облигации: {}
📈 TMOS: {}
💵 LQDT: {}

Итог:
распределять спокойно, без резких покупок.
""".format(rub(amount), rub(bonds_add), rub(tmos_add), rub(lqdt_add))
        except:
            return "Я не понял сумму. Напиши так: /addmoney 50000"

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
ОФЗ купоны за год примерно: {}

Важно:
расчёт приблизительный, без налогов и изменения цен.
""".format(rub(psb_income), rub(bond_income))

    if text == "/meeting":
        return """
👩‍💼 Встреча с инвестиционным консультантом

Стоимость портфеля: {}

Что хорошо:
✅ есть защитная часть
✅ есть ликвидность
✅ есть активы роста

Главные риски:
⚠️ всё в рублях
⚠️ зависимость от российского рынка

Что делать:
1. Портфель держать.
2. Новые деньги — в ОФЗ, TMOS и LQDT.
3. Не продавать на эмоциях.
""".format(rub(total))

    if text == "/psb":
        return """
🏦 Вклад ПСБ

Сумма: 50 000 ₽
Срок: 210 дней
Ставка: 20%

Примерный доход:
около 5 753 ₽ до налогов.
"""

    if text == "/rules":
        return """
📜 Правила инвестирования

1. Не покупать на эмоциях.
2. Не продавать в панике.
3. Не использовать плечи, фьючерсы и шорт.
4. Держать резерв.
5. Проверять портфель раз в месяц.
"""

    if text == "/today":
        return """
🌅 Отчёт на сегодня

✅ Портфель держать.
✅ Резких действий не нужно.
✅ Новые деньги — в ОФЗ, TMOS и LQDT.
"""

    if text == "/news":
        return """
📰 Что важно отслеживать

1. Ставка ЦБ.
2. Доходности ОФЗ.
3. Инфляция.
4. Дивиденды Сбера, МТС и Мосбиржи.

Пока я не читаю новости автоматически.
"""

    return "Не понимаю команду 😊\n\nНапиши /help"

print("Bot started")

while True:
    try:
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
