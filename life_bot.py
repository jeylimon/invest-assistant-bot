import os
import re
import time
import json
import threading
import requests
from datetime import datetime, date, timedelta

BOT_TOKEN = os.environ.get("LIFE_BOT_TOKEN")

last_update_id = 0
subscribed_chats = set()

# ─── Личные данные Саши ───────────────────────────────────────────────────────

HABITS = [
    {"id": "water",    "label": "Вода 💧",          "goal": "8 стаканов в день",    "streak": 0},
    {"id": "workout",  "label": "Тренировка 🏋️",    "goal": "3 раза в неделю",      "streak": 0},
    {"id": "reading",  "label": "Чтение 📚",         "goal": "20 минут в день",      "streak": 0},
    {"id": "walk",     "label": "Прогулка 🚶",       "goal": "30 минут на воздухе",  "streak": 0},
    {"id": "sleep",    "label": "Сон 😴",            "goal": "7-8 часов",            "streak": 0},
    {"id": "no_phone", "label": "Утро без телефона", "goal": "Первый час без соцсетей", "streak": 0},
]

HEALTH_CHECKUPS = [
    {"name": "Стоматолог",           "months": 6,  "last": None, "icon": "🦷"},
    {"name": "Гинеколог",            "months": 12, "last": None, "icon": "👩‍⚕️"},
    {"name": "Общий анализ крови",   "months": 12, "last": None, "icon": "🩸"},
    {"name": "Витамин D",            "months": 12, "last": None, "icon": "☀️"},
    {"name": "Щитовидная железа",    "months": 12, "last": None, "icon": "🔬"},
    {"name": "Проверка зрения",      "months": 24, "last": None, "icon": "👁️"},
    {"name": "Дерматолог",           "months": 12, "last": None, "icon": "🔍"},
]

TRAVEL_WISHLIST = [
    {"place": "Япония",    "status": "мечта",   "budget": 250000},
    {"place": "Бали",      "status": "мечта",   "budget": 180000},
    {"place": "Исландия",  "status": "мечта",   "budget": 200000},
    {"place": "Грузия",    "status": "скоро",   "budget": 60000},
    {"place": "Алтай",     "status": "скоро",   "budget": 40000},
]

BOOKS = [
    {"title": "Думай медленно, решай быстро — Канеман",  "status": "читаю",    "progress": 0},
    {"title": "Атомные привычки — Клир",                  "status": "в планах", "progress": 0},
    {"title": "Психология денег — Хаузел",                "status": "в планах", "progress": 0},
    {"title": "Sapiens — Харари",                         "status": "в планах", "progress": 0},
]

GOALS = [
    {"text": "Инвест-портфель 500 000 ₽",           "category": "финансы",   "done": False, "deadline": date(2026, 12, 31)},
    {"text": "Прочитать 12 книг за 2026 год",        "category": "развитие",  "done": False, "deadline": date(2026, 12, 31)},
    {"text": "Тренироваться 3 раза в неделю",        "category": "здоровье",  "done": False, "deadline": None},
    {"text": "Путешествие в новую страну",            "category": "travel",    "done": False, "deadline": date(2026, 12, 31)},
    {"text": "Выучить что-то новое (курс/навык)",    "category": "развитие",  "done": False, "deadline": None},
]

QUOTES = [
    "Маленький шаг каждый день — через год это будет огромная дистанция.",
    "Не нужно быть лучше всех. Нужно быть лучше себя вчерашней.",
    "Дисциплина — это мост между целью и достижением.",
    "Инвестируй в себя так же, как в портфель: регулярно и долгосрочно.",
    "Сложные вещи становятся лёгкими через привычку.",
    "Твоё утро задаёт тон всему дню.",
    "Прогресс важнее совершенства.",
    "Каждая прочитанная книга — это жизнь другого человека внутри тебя.",
    "Здоровье — это актив. Его тоже нужно накапливать.",
    "Лучший момент начать был вчера. Второй лучший — сейчас.",
]

# ─── Состояние (в памяти) ─────────────────────────────────────────────────────

done_today = {}      # {"2026-06-29": {"water", "workout"}}
streaks = {h["id"]: 0 for h in HABITS}
water_count = {}     # {"2026-06-29": 3}
sleep_log = {}       # {"2026-06-29": 7.5}
mood_log = {}        # {"2026-06-29": "хорошо"}
notes = []           # [{date, text}]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def today_str():
    return date.today().isoformat()

def get_done():
    return done_today.get(today_str(), set())

def mark_done(habit_id):
    t = today_str()
    if t not in done_today:
        done_today[t] = set()
    done_today[t].add(habit_id)
    # Update streak
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if habit_id in done_today.get(yesterday, set()):
        streaks[habit_id] = streaks.get(habit_id, 0) + 1
    else:
        streaks[habit_id] = 1

def progress_bar(done, total, width=10):
    filled = int(done / total * width) if total else 0
    return "█" * filled + "░" * (width - filled)

def quote_of_day():
    idx = date.today().toordinal() % len(QUOTES)
    return QUOTES[idx]

def fmt_date(d):
    months = ["янв", "фев", "мар", "апр", "май", "июн",
              "июл", "авг", "сен", "окт", "ноя", "дек"]
    return "{} {}".format(d.day, months[d.month - 1])

def find_habit(text):
    text = text.lower().strip()
    aliases = {
        "вода": "water", "воду": "water", "water": "water",
        "тренировка": "workout", "трен": "workout", "спорт": "workout", "workout": "workout",
        "чтение": "reading", "читала": "reading", "книга": "reading", "reading": "reading",
        "прогулка": "walk", "ходила": "walk", "walk": "walk",
        "сон": "sleep", "спала": "sleep", "sleep": "sleep",
        "телефон": "no_phone", "утро": "no_phone", "phone": "no_phone",
    }
    return aliases.get(text)

# ─── Telegram API ─────────────────────────────────────────────────────────────

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
            [{"text": "/day"}, {"text": "/habits"}],
            [{"text": "/health"}, {"text": "/travel"}],
            [{"text": "/learn"}, {"text": "/goals"}],
            [{"text": "/evening"}, {"text": "/help"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }

# ─── Proactive: утреннее и вечернее ──────────────────────────────────────────

last_morning = None
last_evening = None

def check_morning():
    global last_morning
    now = datetime.utcnow()
    today = now.date()
    if (now.hour + 3) % 24 == 8 and last_morning != today and subscribed_chats:
        last_morning = today
        for chat_id in list(subscribed_chats):
            send_message(chat_id, cmd_day(), main_keyboard())

def check_evening():
    global last_evening
    now = datetime.utcnow()
    today = now.date()
    if (now.hour + 3) % 24 == 21 and last_evening != today and subscribed_chats:
        last_evening = today
        for chat_id in list(subscribed_chats):
            send_message(chat_id, cmd_evening(), main_keyboard())

# ─── Commands ─────────────────────────────────────────────────────────────────

def cmd_day():
    done = get_done()
    water = water_count.get(today_str(), 0)
    total_habits = len(HABITS)
    done_count = len(done)

    now_msk = (datetime.utcnow().hour + 3) % 24
    if now_msk < 12:
        greeting = "☀️ Доброе утро, Саша!"
    elif now_msk < 18:
        greeting = "🌤 Добрый день, Саша!"
    else:
        greeting = "🌙 Добрый вечер, Саша!"

    lines = [
        greeting,
        "",
        "💬 «{}»".format(quote_of_day()),
        "",
        "📋 Привычки на сегодня [{}/{}]:".format(done_count, total_habits),
    ]

    for h in HABITS:
        icon = "✅" if h["id"] in done else "⬜"
        streak = streaks.get(h["id"], 0)
        streak_str = " 🔥{}".format(streak) if streak >= 2 else ""
        lines.append("  {} {}{}".format(icon, h["label"], streak_str))

    lines.append("")
    lines.append("💧 Вода: {}/8 стаканов  {}".format(water, progress_bar(water, 8)))

    # Ближайшие обследования
    upcoming = []
    for ch in HEALTH_CHECKUPS:
        if ch["last"] is None:
            upcoming.append(ch)
    if upcoming:
        lines.append("")
        lines.append("🏥 Напоминание: {} — давно не было".format(upcoming[0]["name"]))

    # Цели
    active_goals = [g for g in GOALS if not g["done"]]
    if active_goals:
        lines.append("")
        lines.append("🎯 Фокус: {}".format(active_goals[0]["text"]))

    lines.append("")
    lines.append("Отметить привычку: /done вода  |  /done тренировка")
    lines.append("Итоги дня вечером: /evening")

    return "\n".join(lines)

def cmd_habits():
    done = get_done()
    lines = ["🔄 Привычки Саши\n"]

    for h in HABITS:
        icon = "✅" if h["id"] in done else "⬜"
        streak = streaks.get(h["id"], 0)
        streak_str = "  🔥 {} дней подряд".format(streak) if streak >= 2 else ""
        lines.append("{} {} — {}{}".format(icon, h["label"], h["goal"], streak_str))

    done_count = len(done)
    total = len(HABITS)
    lines.append("")
    lines.append("Сегодня: {}/{} {}".format(done_count, total, progress_bar(done_count, total)))

    lines.append("")
    lines.append("Отметить: /done вода · /done тренировка · /done чтение")
    lines.append("           /done прогулка · /done сон · /done телефон")
    return "\n".join(lines)

def cmd_done(args):
    habit_id = find_habit(args.strip())
    if not habit_id:
        return (
            "Не нашла привычку. Попробуй:\n"
            "/done вода\n"
            "/done тренировка\n"
            "/done чтение\n"
            "/done прогулка\n"
            "/done сон\n"
            "/done телефон"
        )
    done = get_done()
    if habit_id in done:
        h = next(h for h in HABITS if h["id"] == habit_id)
        return "✅ {} уже отмечена сегодня!".format(h["label"])

    mark_done(habit_id)
    h = next(h for h in HABITS if h["id"] == habit_id)
    streak = streaks.get(habit_id, 1)
    streak_msg = ""
    if streak >= 7:
        streak_msg = "\n🔥 Невероятно! {} дней подряд!".format(streak)
    elif streak >= 3:
        streak_msg = "\n🔥 {} дней подряд — так держать!".format(streak)
    elif streak >= 2:
        streak_msg = "\n🔥 {} дня подряд!".format(streak)

    done_count = len(get_done())
    total = len(HABITS)
    return "✅ {} выполнена!{}\n\nСегодня: {}/{} привычек {}".format(
        h["label"], streak_msg, done_count, total, progress_bar(done_count, total))

def cmd_water(args):
    try:
        n = int(args.strip())
        if n <= 0 or n > 20:
            raise ValueError
    except:
        return "Укажи количество стаканов. Пример: /water 3"

    t = today_str()
    water_count[t] = water_count.get(t, 0) + n
    total = water_count[t]
    bar = progress_bar(total, 8)

    if total >= 8:
        msg = "🎉 Норма выполнена! {} стаканов".format(total)
    else:
        msg = "💧 Выпила {} стаканов. Осталось: {} {}".format(total, max(0, 8 - total), bar)
    return msg

def cmd_sleep(args):
    try:
        h = float(args.strip().replace(",", "."))
        if h <= 0 or h > 24:
            raise ValueError
    except:
        return "Укажи часы сна. Пример: /sleep 7.5"

    sleep_log[today_str()] = h
    if h >= 7:
        comment = "Отлично! Организм скажет спасибо."
    elif h >= 6:
        comment = "Неплохо, но старайся спать хотя бы 7 часов."
    else:
        comment = "Маловато. Сон — основа здоровья и продуктивности."
    return "😴 Сон записан: {:.1f} ч\n{}".format(h, comment)

def cmd_health():
    water = water_count.get(today_str(), 0)
    sleep_h = sleep_log.get(today_str())
    lines = ["🏥 Здоровье Саши\n"]

    lines.append("💧 Вода сегодня: {}/8 стаканов  {}".format(water, progress_bar(water, 8)))
    if sleep_h:
        lines.append("😴 Сон прошлой ночью: {:.1f} ч".format(sleep_h))
    else:
        lines.append("😴 Сон: не записан → /sleep 8")
    lines.append("")

    lines.append("📅 Обследования:")
    for ch in HEALTH_CHECKUPS:
        if ch["last"]:
            next_date = ch["last"] + timedelta(days=ch["months"] * 30)
            days_left = (next_date - date.today()).days
            if days_left < 0:
                status = "⚠️ просрочено на {} дн.".format(abs(days_left))
            elif days_left <= 30:
                status = "⏰ через {} дн.".format(days_left)
            else:
                status = "✅ через {} дн.".format(days_left)
        else:
            status = "❓ не записано"
        lines.append("  {} {} — {}".format(ch["icon"], ch["name"], status))

    lines.append("")
    lines.append("Записать обследование: /checkup стоматолог 2026-06-15")
    lines.append("Вода: /water 2  |  Сон: /sleep 7.5")
    return "\n".join(lines)

def cmd_checkup(args):
    parts = args.strip().split()
    if len(parts) < 2:
        return "Пример: /checkup стоматолог 2026-06-15"

    name_input = parts[0].lower()
    date_str = parts[1]

    try:
        checkup_date = date.fromisoformat(date_str)
    except:
        return "Формат даты: ГГГГ-ММ-ДД. Пример: /checkup стоматолог 2026-06-15"

    for ch in HEALTH_CHECKUPS:
        if name_input in ch["name"].lower():
            ch["last"] = checkup_date
            next_date = checkup_date + timedelta(days=ch["months"] * 30)
            return "✅ {} записан: {}\nСледующий: {}".format(
                ch["name"], fmt_date(checkup_date), fmt_date(next_date))

    return "Не нашла обследование '{}'. Напиши /health чтобы увидеть список.".format(parts[0])

def cmd_travel():
    lines = ["✈️ Путешествия Саши\n"]

    soon = [t for t in TRAVEL_WISHLIST if t["status"] == "скоро"]
    dreams = [t for t in TRAVEL_WISHLIST if t["status"] == "мечта"]

    if soon:
        lines.append("📍 Скоро:")
        for t in soon:
            lines.append("  • {} — бюджет ~{:,} ₽".format(t["place"], t["budget"]).replace(",", " "))
        lines.append("")

    if dreams:
        lines.append("🌍 Хочу побывать:")
        for t in dreams:
            lines.append("  • {} — бюджет ~{:,} ₽".format(t["place"], t["budget"]).replace(",", " "))
        lines.append("")

    lines.append("Добавить место: /add travel Марокко 120000")
    lines.append("Переместить в 'скоро': /soon Грузия")
    return "\n".join(lines)

def cmd_learn():
    lines = ["📚 Обучение и чтение\n"]

    current = [b for b in BOOKS if b["status"] == "читаю"]
    planned = [b for b in BOOKS if b["status"] == "в планах"]
    done_books = [b for b in BOOKS if b["status"] == "прочитано"]

    if current:
        lines.append("📖 Сейчас читаю:")
        for b in current:
            p = b["progress"]
            lines.append("  {} {}%  {}".format(b["title"], p, progress_bar(p, 100)))
        lines.append("  Обновить прогресс: /progress 35")
        lines.append("")

    if planned:
        lines.append("📋 Список чтения:")
        for i, b in enumerate(planned, 1):
            lines.append("  {}. {}".format(i, b["title"]))
        lines.append("")

    if done_books:
        lines.append("✅ Прочитано в этом году: {} книг".format(len(done_books)))
        lines.append("  Цель: 12 книг  {}".format(progress_bar(len(done_books), 12)))
        lines.append("")

    lines.append("Добавить книгу: /add book Название книги")
    lines.append("Отметить прочитанной: /done книга")
    return "\n".join(lines)

def cmd_goals():
    lines = ["🎯 Цели Саши 2026\n"]

    by_cat = {}
    for g in GOALS:
        cat = g["category"]
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(g)

    cat_icons = {
        "финансы": "💰",
        "здоровье": "💪",
        "развитие": "📚",
        "travel": "✈️",
    }

    for cat, goals in by_cat.items():
        icon = cat_icons.get(cat, "🎯")
        lines.append("{} {}:".format(icon, cat.capitalize()))
        for g in goals:
            icon2 = "✅" if g["done"] else "◻️"
            deadline = "  (до {})".format(fmt_date(g["deadline"])) if g["deadline"] else ""
            lines.append("  {} {}{}".format(icon2, g["text"], deadline))
        lines.append("")

    done_count = sum(1 for g in GOALS if g["done"])
    lines.append("Выполнено: {}/{}  {}".format(done_count, len(GOALS), progress_bar(done_count, len(GOALS))))
    lines.append("")
    lines.append("Добавить цель: /add goal Моя новая цель")
    lines.append("Отметить выполненной: /goal done 1")
    return "\n".join(lines)

def cmd_evening():
    done = get_done()
    water = water_count.get(today_str(), 0)
    sleep_h = sleep_log.get(today_str())

    done_count = len(done)
    total = len(HABITS)
    score = int(done_count / total * 100)

    if score == 100:
        result = "🌟 Идеальный день! Ты молодец!"
    elif score >= 70:
        result = "💪 Отличный день! Почти всё выполнила."
    elif score >= 40:
        result = "👍 Неплохо. Завтра чуть больше!"
    else:
        result = "🌱 Сложный день — бывает. Завтра новый старт."

    lines = [
        "🌙 Итоги дня\n",
        result,
        "",
        "✅ Привычки: {}/{} {}".format(done_count, total, progress_bar(done_count, total)),
    ]

    for h in HABITS:
        icon = "✅" if h["id"] in done else "☐"
        lines.append("  {} {}".format(icon, h["label"]))

    lines.append("")
    lines.append("💧 Вода: {}/8 стаканов".format(water))

    if sleep_h:
        lines.append("😴 Сон: {:.1f} ч".format(sleep_h))

    lines.append("")
    lines.append("💬 Как прошёл день? Напиши /mood хорошо (или сложно/средне)")
    lines.append("До завтра! Новый день — новые возможности. 🌅")
    return "\n".join(lines)

def cmd_mood(args):
    mood = args.strip().lower()
    if not mood:
        return "Как настроение? /mood хорошо  или  /mood сложно  или  /mood средне"
    mood_log[today_str()] = mood

    responses = {
        "хорошо": "Это прекрасно! Отличный день — запомни это ощущение. ✨",
        "отлично": "Вот это да! Такие дни заряжают надолго. 🌟",
        "супер": "Невероятно! Ты сияешь! 🌟",
        "средне": "Обычный день — тоже ценность. Главное — ты двигаешься вперёд. 💪",
        "сложно": "Понимаю. Сложные дни тоже делают нас сильнее. Отдохни и обнови силы. 🤗",
        "плохо": "Жаль слышать. Это пройдёт. Сделай что-то маленькое для себя прямо сейчас. 💙",
    }
    response = responses.get(mood, "Записала настроение: {}. Спасибо что делишься! 💙".format(mood))
    return response

def cmd_add(args):
    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        return (
            "Что добавить?\n\n"
            "/add travel Марокко 120000\n"
            "/add book Название книги\n"
            "/add goal Моя новая цель"
        )

    category = parts[0].lower()
    content = parts[1]

    if category == "travel":
        sub = content.split()
        place = sub[0]
        try:
            budget = int(sub[1]) if len(sub) > 1 else 0
        except:
            budget = 0
        TRAVEL_WISHLIST.append({"place": place, "status": "мечта", "budget": budget})
        return "✅ {} добавлена в список путешествий!".format(place)

    if category == "book":
        BOOKS.append({"title": content, "status": "в планах", "progress": 0})
        return "✅ Книга добавлена: {}".format(content)

    if category == "goal":
        GOALS.append({"text": content, "category": "личное", "done": False, "deadline": None})
        return "✅ Цель добавлена: {}".format(content)

    return "Категория не найдена. Используй: travel, book, goal"

def cmd_progress(args):
    try:
        pct = int(args.strip())
        if pct < 0 or pct > 100:
            raise ValueError
    except:
        return "Укажи процент. Пример: /progress 45"

    current = next((b for b in BOOKS if b["status"] == "читаю"), None)
    if not current:
        return "Нет активной книги. Начни читать — добавь: /add book Название"

    current["progress"] = pct
    if pct == 100:
        current["status"] = "прочитано"
        done_books = sum(1 for b in BOOKS if b["status"] == "прочитано")
        return "🎉 Книга прочитана! Это уже {} книга в этом году!\n{}  {}".format(
            done_books, current["title"], progress_bar(done_books, 12))

    return "📖 Прогресс обновлён: {}%  {}\n{}".format(
        pct, progress_bar(pct, 100), current["title"])

def cmd_soon(args):
    place = args.strip()
    for t in TRAVEL_WISHLIST:
        if place.lower() in t["place"].lower():
            t["status"] = "скоро"
            return "✈️ {} переместила в 'скоро'! Начинай планировать!".format(t["place"])
    return "Место не найдено: {}".format(place)

def cmd_help():
    return (
        "🤖 Life OS Саши\n\n"
        "📋 ЕЖЕДНЕВНОЕ:\n"
        "/day — обзор дня, привычки, цитата\n"
        "/habits — список привычек и стрики\n"
        "/done ПРИВЫЧКА — отметить выполненной\n"
        "/evening — итоги дня\n"
        "/mood хорошо — записать настроение\n\n"
        "💧 ЗДОРОВЬЕ:\n"
        "/health — обзор здоровья и обследования\n"
        "/water 3 — записать стаканы воды\n"
        "/sleep 7.5 — записать часы сна\n"
        "/checkup стоматолог 2026-06-15 — записать визит\n\n"
        "📚 РАЗВИТИЕ:\n"
        "/learn — книги и обучение\n"
        "/progress 45 — обновить прогресс чтения\n\n"
        "✈️ ПУТЕШЕСТВИЯ:\n"
        "/travel — список мест\n"
        "/soon Грузия — переместить в 'скоро'\n\n"
        "🎯 ЦЕЛИ:\n"
        "/goals — все цели\n\n"
        "➕ ДОБАВИТЬ:\n"
        "/add book Название\n"
        "/add travel Токио 200000\n"
        "/add goal Моя цель\n\n"
        "/subscribe — авто: 8:00 утро, 21:00 вечер"
    )

def cmd_subscribe(chat_id):
    subscribed_chats.add(chat_id)
    return (
        "✅ Подписка активирована!\n\n"
        "☀️ 8:00 МСК — утренний обзор и привычки\n"
        "🌙 21:00 МСК — итоги дня\n\n"
        "Отключить: /unsubscribe"
    )

def cmd_unsubscribe(chat_id):
    subscribed_chats.discard(chat_id)
    return "🔕 Оповещения отключены. Включить: /subscribe"

# ─── Router ───────────────────────────────────────────────────────────────────

def answer(text, chat_id):
    t = text.strip()
    if t in ("/start", "/help"):    return cmd_help()
    if t == "/day":                 return cmd_day()
    if t == "/habits":              return cmd_habits()
    if t == "/health":              return cmd_health()
    if t == "/travel":              return cmd_travel()
    if t == "/learn":               return cmd_learn()
    if t == "/goals":               return cmd_goals()
    if t == "/evening":             return cmd_evening()
    if t == "/subscribe":           return cmd_subscribe(chat_id)
    if t == "/unsubscribe":         return cmd_unsubscribe(chat_id)
    if t.startswith("/done"):
        parts = t.split(maxsplit=1)
        return cmd_done(parts[1] if len(parts) > 1 else "")
    if t.startswith("/water"):
        parts = t.split(maxsplit=1)
        return cmd_water(parts[1] if len(parts) > 1 else "")
    if t.startswith("/sleep"):
        parts = t.split(maxsplit=1)
        return cmd_sleep(parts[1] if len(parts) > 1 else "")
    if t.startswith("/mood"):
        parts = t.split(maxsplit=1)
        return cmd_mood(parts[1] if len(parts) > 1 else "")
    if t.startswith("/add"):
        parts = t.split(maxsplit=1)
        return cmd_add(parts[1] if len(parts) > 1 else "")
    if t.startswith("/progress"):
        parts = t.split(maxsplit=1)
        return cmd_progress(parts[1] if len(parts) > 1 else "")
    if t.startswith("/checkup"):
        parts = t.split(maxsplit=1)
        return cmd_checkup(parts[1] if len(parts) > 1 else "")
    if t.startswith("/soon"):
        parts = t.split(maxsplit=1)
        return cmd_soon(parts[1] if len(parts) > 1 else "")
    return "Не поняла команду. Напиши /help"

# ─── Main loop ────────────────────────────────────────────────────────────────

print("SashaLifeBot v1 started")

while True:
    try:
        if not BOT_TOKEN:
            print("LIFE_BOT_TOKEN missing")
            time.sleep(10)
            continue

        check_morning()
        check_evening()

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
