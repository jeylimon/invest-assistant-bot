# invest-assistant-bot

## IELTS Logbook — главный файл для редактирования

**Файл:** `docs/ielts.html`  
**Live URL:** https://jeylimon.github.io/invest-assistant-bot/ielts.html  
**Ветка разработки:** `claude/test-coverage-analysis-i9r194`  
**Деплой:** push в `main` → GitHub Pages обновляется автоматически

### Что это

Standalone PWA для подготовки к IELTS. Один HTML-файл, без зависимостей. Все данные хранятся в `localStorage` браузера (ключ: `ielts_logbook_v1`).

### Вкладки

| Вкладка | Назначение |
|---------|-----------|
| Неделя | Цели на неделю + 7 дней занятий с отметкой и заметками |
| Баллы | Чекпойнты (тип задания, band, заметки) + SVG-спарклайн |
| Ошибки | Банк ошибок с типом, фильтрами, флагом «знаю» |
| Слова | Словарь с флэш-картами (3D flip) и списком |

### Как вносить изменения по ходу обучения

Когда пользователь говорит «добавь слово / ошибку / результат» — нужно:
1. Найти нужный массив в `seedIfEmpty()` или напрямую в разделе с данными
2. Добавить объект с полями (см. структуру ниже)
3. Сохранить `docs/ielts.html`
4. Запустить: `git add docs/ielts.html && git commit -m "..." && git push origin claude/test-coverage-analysis-i9r194`
5. Затем push в main: `git push origin claude/test-coverage-analysis-i9r194:main` (или через temp-branch)

### Структура данных

```js
// Чекпойнт (вкладка Баллы)
{ id: uid(), date: 'YYYY-MM-DD', type: 'Writing Task 2', band: '6.0', notes: '...' }

// Ошибка (вкладка Ошибки)
{ id: uid(), date: 'YYYY-MM-DD', wrong: '...', right: '...', type: 'Грамматика', ctx: '...', learned: false }
// type: 'Грамматика' | 'Коллокация' | 'Лексика' | 'Стиль'

// Слово (вкладка Слова)
{ id: uid(), date: 'YYYY-MM-DD', word: '...', trans: '...', ex: '...', cat: '...', learned: false }
// cat: 'Академическая лексика' | 'Коллокация' | 'Связки и переходы' | 'Идиома' | 'Другое'
```

### Seed данные (уже внесены)

**Баллы:** 2 Writing Task 2 (5.5 и 6.0) — Nature or nurture, Longer prison sentences  
**Ошибки:** 3 записи — косвенный вопрос, инфинитив цели, unconditional love  
**Слова:** to mitigate, a contentious issue, in stark contrast to, to exacerbate

### Безопасность

- Весь пользовательский ввод экранируется через `esc()` перед вставкой в innerHTML
- `confirm()` не используется (заменён на inline confirm-bar)
- Нет внешних запросов, нет зависимостей
- `save()` обёрнут в try/catch

### Деплой в main

```bash
git fetch origin main
git checkout -b temp-main origin/main
git checkout claude/test-coverage-analysis-i9r194 -- docs/ielts.html
git commit -m "Update IELTS Logbook"
git push origin temp-main:main
git checkout claude/test-coverage-analysis-i9r194
git branch -D temp-main
```
