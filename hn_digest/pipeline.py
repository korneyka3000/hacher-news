"""Оркестрация: сбор → антидубли → курация → форматирование → доставка.

При любом падении шлёт уведомление в Telegram (если возможно) и выходит с
ненулевым кодом, чтобы launchd зафиксировал ошибку в логах.
"""

from __future__ import annotations

import os
import subprocess
import sys
import traceback
from datetime import datetime

from .config import Settings
from .curation import curate
from .dedup import SeenStore
from .formatting import build_messages
from .logging_setup import get_logger, setup_logging
from .scheduling import is_within_window
from .sources import enrich_links, fetch_candidates
from .telegram import TelegramClient

log = get_logger(__name__)


def run(dry_run: bool = False, scheduled: bool = False) -> None:
    settings = Settings.from_env()

    # В плановом режиме (--scheduled из launchd) пропускаем поздний запуск:
    # если Mac спал и проснулся сильно позже цели — выжимка уже неактуальна.
    if scheduled and not is_within_window(
        datetime.now(),
        settings.schedule_hour,
        settings.schedule_minute,
        settings.run_window_minutes,
    ):
        log.info(
            "Пропуск: запуск позже окна (%02d:%02d + %d мин) — вероятно, машина спала. "
            "Ничего не отправляю.",
            settings.schedule_hour,
            settings.schedule_minute,
            settings.run_window_minutes,
        )
        return

    seen = SeenStore(settings.seen_path, settings.seen_ttl_days)

    candidates = fetch_candidates(settings)
    fresh = seen.filter_new(candidates)
    # Обогащаем ТОЛЬКО свежие истории — не тратим сеть на будущие дубли.
    enrich_links(fresh, settings.enrich_top_n)
    items = curate(fresh, settings)
    messages = build_messages(items)
    log.info(
        "Итог: кандидатов=%s, свежих=%s, отобрано=%s, сообщений=%s",
        len(candidates),
        len(fresh),
        len(items),
        len(messages),
    )

    if dry_run:
        print("\n\n===== DRY RUN (в Telegram не отправлено) =====\n")
        print("\n\n----- следующее сообщение -----\n\n".join(messages))
        print(f"\n[dry-run] сообщений: {len(messages)}, историй к отправке: {len(items)}")
        return

    settings.require_telegram()
    client = TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)
    client.send_all(messages)
    # Помечаем отправленным только то, что реально ушло.
    seen.mark_sent(items)


def health_check() -> bool:
    """Локальная самопроверка окружения (без сети/HN/отправки). True = всё ок."""
    ok = True

    def check(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        print(f"{'✅' if passed else '❌'} {name}" + (f" — {detail}" if detail else ""))
        ok = ok and passed

    settings = Settings.from_env()

    has_tg = bool(settings.telegram_bot_token and settings.telegram_chat_id)
    check("Telegram-креды", has_tg, "заданы" if has_tg else "не заданы (см. .env)")

    try:
        proc = subprocess.run(
            [settings.claude_bin, "--version"], capture_output=True, text=True, timeout=30
        )
        ver = (proc.stdout or proc.stderr or "").strip().splitlines()
        check(f"Claude Code ({settings.claude_bin})", proc.returncode == 0, ver[0] if ver else "")
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        check(f"Claude Code ({settings.claude_bin})", False, str(exc))

    state_dir = settings.seen_path.parent
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        writable = os.access(state_dir, os.W_OK)
        check(
            f"Каталог state ({state_dir})",
            writable,
            "доступен на запись" if writable else "нет доступа на запись",
        )
    except OSError as exc:
        check(f"Каталог state ({state_dir})", False, str(exc))

    if os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "⚠️  Задан ANTHROPIC_API_KEY — при подписке Max это может ломать "
            "`claude -p` (401). Убери из окружения, если курация падает."
        )

    print("\nИтог:", "готово к работе ✅" if ok else "есть проблемы ❌")
    return ok


def _notify_failure(exc: BaseException) -> None:
    """Пытается сообщить о падении в Telegram (best-effort)."""
    try:
        settings = Settings.from_env()
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            return
        client = TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)
        client.send_error(f"⚠️ HN дайджест упал:\n{type(exc).__name__}: {exc}")
    except Exception as notify_exc:  # noqa: BLE001
        log.error("Уведомление о падении не отправлено: %s", notify_exc)


def main() -> None:
    setup_logging()
    if "--health" in sys.argv:
        sys.exit(0 if health_check() else 1)

    dry_run = "--dry-run" in sys.argv
    scheduled = "--scheduled" in sys.argv
    log.info("=== HN Digest старт%s ===", " (dry-run)" if dry_run else "")
    try:
        run(dry_run=dry_run, scheduled=scheduled)
    except SystemExit as exc:
        # SystemExit несёт понятное сообщение об ошибке конфигурации/окружения.
        if exc.code not in (0, None):
            log.error("%s", exc)
            _notify_failure(RuntimeError(str(exc.code)))
        raise
    except Exception as exc:  # noqa: BLE001
        log.error("Непойманная ошибка:\n%s", traceback.format_exc())
        _notify_failure(exc)
        sys.exit(1)
    log.info("=== HN Digest готово ===")
