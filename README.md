# HN Digest

Утренний дайджест по IT из Hacker News в Telegram. Каждый день в 9:00:

1. Тянет свежие истории с Hacker News (фронтпейдж + Show HN через Algolia API).
2. Отсеивает те, что **уже присылались раньше** (антидубли).
3. Прогоняет остальное через **Claude Code** (`claude -p`) — тот отбирает стоящее
   (стартапы, идеи, крутые фичи), пишет разбор и вердикт
   «🟢 Полезно / 🟡 На заметку / 🔴 Мимо» на русском.
4. Постит результат в Telegram-бота (`@KorneyBurau_bot`).
5. Если прогон падает — бот присылает уведомление об ошибке.

Курация идёт через Claude Code CLI, то есть покрывается подпиской **Max** —
отдельный платный доступ к Anthropic API не нужен.

## Структура

```
hn_digest/
├── __main__.py       # точка входа: python -m hn_digest
├── config.py         # настройки из .env → dataclass Settings
├── logging_setup.py  # логирование в stderr
├── models.py         # Story / CuratedItem
├── sources.py        # сбор кандидатов с Hacker News
├── dedup.py          # SeenStore — антидубли (state/seen.json)
├── curation.py       # курация через claude -p
├── formatting.py     # сборка Telegram-сообщений (чанкинг < 4096)
├── telegram.py       # клиент Telegram + уведомление об ошибке
└── pipeline.py       # оркестрация + обработка падений
```

Состояние антидублей хранится в `state/seen.json` (в git не попадает).

## Требования

- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [Claude Code](https://claude.com/claude-code) с активной подпиской Pro/Max,
  залогиненный (`claude` → `/login`). Проверка: `claude -p "ответь ок"`.
- Python ≥ 3.10 (uv поставит при необходимости).

Зависимость `httpx` объявлена в `pyproject.toml` — `uv run` поднимет окружение сам.

## Настройка

1. Скопируй `.env.example` → `.env` и впиши значения (токен уже проставлен).
2. Проверь пути и при необходимости поправь `run.sh`:
   ```bash
   which uv
   which claude
   ```

## Запуск вручную

```bash
# Тест без отправки — печатает дайджест в консоль:
uv run python -m hn_digest --dry-run

# Боевой прогон — постит в Telegram и запоминает отправленное:
uv run python -m hn_digest
```

> ⚠️ `--dry-run` не помечает истории как отправленные — они придут при боевом прогоне.

## Автозапуск в 9:00 (launchd)

```bash
cp com.korney.hndigest.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.korney.hndigest.plist
launchctl list | grep hndigest        # проверить, что загрузился
launchctl start com.korney.hndigest   # прогнать сразу, не дожидаясь 9:00
tail -f hn_digest.log hn_digest.err   # логи
```

Отключить: `launchctl unload ~/Library/LaunchAgents/com.korney.hndigest.plist`.

> launchd-агент запускается, только когда ты залогинен. Если Mac спал в 9:00,
> задача выполнится при следующем пробуждении.
>
> Важно: launchd наследует окружение логина. Если где-то в профиле (`~/.zshrc` и т.п.)
> выставлен битый `ANTHROPIC_API_KEY`, `claude -p` упадёт с 401 — убери его оттуда.

## Настройки (`.env`)

| Переменная            | По умолчанию      | Смысл                                             |
|-----------------------|-------------------|---------------------------------------------------|
| `TELEGRAM_BOT_TOKEN`  | —                 | Токен бота от @BotFather                          |
| `TELEGRAM_CHAT_ID`    | —                 | Куда постить (твой chat id)                        |
| `CLAUDE_BIN`          | `claude`          | Путь к бинарю Claude Code                          |
| `CLAUDE_MODEL`        | дефолт            | Модель курации, напр. `sonnet`                    |
| `HN_MIN_POINTS`       | `20`              | Мин. рейтинг (Show HN проходит без порога)         |
| `HN_LOOKBACK_HOURS`   | `36`              | За сколько часов брать истории                     |
| `SEEN_TTL_DAYS`       | `30`              | Сколько дней помнить отправленное                  |
| `SEEN_PATH`           | `state/seen.json` | Файл истории антидублей                            |

## Разработка

Тесты (чистая логика, без сети/claude/telegram):

```bash
uv run pytest
```

Продолжаешь развивать через CLI-агента? Контекст, конвенции и точки расширения —
в [`AGENTS.md`](AGENTS.md).

## Безопасность

`.env` с токеном исключён из git. Если токен утёк — отзови у @BotFather (`/revoke`).
