# HN Digest

Утренний дайджест по IT из Hacker News в Telegram. Каждый день в 9:00:

1. Тянет свежие истории с Hacker News (фронтпейдж + Show HN через Algolia API).
2. Отсеивает те, что **уже присылались раньше** (антидубли).
3. Обогащает ссылочные истории мета-контекстом страницы (title/description),
   чтобы у LLM был не только заголовок, а суть статьи (без LLM, best-effort).
4. Прогоняет остальное через **Claude Code** (`claude -p`) — тот отбирает стоящее
   (стартапы, идеи, крутые фичи), пишет разбор и вердикт
   «🟢 Полезно / 🟡 На заметку / 🔴 Мимо» на русском.
5. Постит результат в Telegram-бота (`@KorneyBurau_bot`).
6. Если прогон падает — бот присылает уведомление об ошибке.

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

## Быстрые команды (Taskfile)

Удобная обёртка на [go-task](https://taskfile.dev) (`brew install go-task`):

```bash
task            # список команд
task dry        # тестовый прогон без отправки (~5 постов, в консоль)
task run        # боевой прогон — постит в Telegram
task test       # юнит-тесты
task health     # самопроверка окружения (claude, креды, state/)
task usage      # сводка расхода токенов/цены курации
task install    # поставить автозапуск в 9:00 (launchd)
task uninstall  # убрать автозапуск
task logs       # хвост логов
```

## Запуск вручную

```bash
# Тест без отправки — печатает дайджест в консоль:
uv run python -m hn_digest --dry-run

# Боевой прогон — постит в Telegram и запоминает отправленное:
uv run python -m hn_digest

# Самопроверка окружения (без сети и отправки):
uv run python -m hn_digest --health
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

Проще через Taskfile: `task install` / `task uninstall`.

> launchd-агент запускается, только когда ты залогинен. Если Mac спал в 9:00,
> launchd выполнит задачу при следующем пробуждении — но `run.sh` передаёт
> `--scheduled`, и **гард окна пропустит поздний прогон** (по умолчанию всё, что
> позже 9:00 + 90 мин). Так устаревшая утренняя выжимка не приходит днём. Ширина
> окна настраивается `RUN_WINDOW_MINUTES`, время цели — `SCHEDULE_HOUR/MINUTE`.
> Ручные прогоны (`task run`, без `--scheduled`) гард не трогает.
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
| `ENRICH_TOP_N`        | `25`              | Сколько top-ссылок обогащать мета-контекстом (0=выкл) |
| `SEEN_TTL_DAYS`       | `30`              | Сколько дней помнить отправленное                  |
| `SEEN_PATH`           | `state/seen.json` | Файл истории антидублей                            |
| `USAGE_PATH`          | `state/usage.jsonl` | Леджер токенов/цены курации (`task usage`)       |
| `SCHEDULE_HOUR`       | `9`               | Час цели запуска (для гарда окна)                  |
| `SCHEDULE_MINUTE`     | `0`               | Минута цели запуска                                |
| `RUN_WINDOW_MINUTES`  | `90`              | Насколько поздний `--scheduled`-прогон ещё шлём    |

## Учёт токенов / цены курации

Курация идёт через `claude -p --output-format json` — каждый прогон пишет строку в
`state/usage.jsonl` (токены in/out, `total_cost_usd`, длительность). `task usage`
(или `python -m hn_digest.usage_report`) показывает сводку. Это заранее даёт понять
цену действия, если однажды переезжать с подписки Max на платный Anthropic API.

## Разработка

Инструменты (astral): **ruff** (линтер+форматтер) и **ty** (тайпчекер) — в dev-группе,
`uv sync` их поднимет. Единый гейт перед коммитом:

```bash
task check      # ruff check + ruff format --check + ty check + pytest
```

Отдельные команды:

```bash
task test       # uv run pytest — чистая логика, без сети/claude/telegram
task lint       # uv run ruff check --fix .
task fmt        # uv run ruff format .
task typecheck  # uv run ty check
```

Продолжаешь развивать через CLI-агента? Контекст, конвенции и точки расширения —
в [`AGENTS.md`](AGENTS.md).

## Безопасность

`.env` с токеном исключён из git. Если токен утёк — отзови у @BotFather (`/revoke`).
