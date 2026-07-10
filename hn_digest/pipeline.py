"""Оркестрация: сбор → антидубли → курация → форматирование → доставка.

При любом падении шлёт уведомление в Telegram (если возможно) и выходит с
ненулевым кодом, чтобы launchd зафиксировал ошибку в логах.
"""

from __future__ import annotations

import sys
import traceback

from .config import Settings
from .curation import curate
from .dedup import SeenStore
from .formatting import build_messages
from .logging_setup import get_logger, setup_logging
from .sources import fetch_candidates
from .telegram import TelegramClient

log = get_logger(__name__)


def run(dry_run: bool = False) -> None:
    settings = Settings.from_env()
    seen = SeenStore(settings.seen_path, settings.seen_ttl_days)

    candidates = fetch_candidates(settings)
    fresh = seen.filter_new(candidates)
    items = curate(fresh, settings)
    messages = build_messages(items)

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
    dry_run = "--dry-run" in sys.argv
    log.info("=== HN Digest старт%s ===", " (dry-run)" if dry_run else "")
    try:
        run(dry_run=dry_run)
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
