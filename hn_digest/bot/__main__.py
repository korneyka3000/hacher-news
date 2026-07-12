"""Локальный запуск бота в polling-режиме: `python -m hn_digest.bot`.

Для разработки без публичного URL. В проде используется webhook (см. main.py).
"""

from __future__ import annotations

import asyncio

from ..config import Settings
from ..db import make_engine, make_sessionmaker
from ..logging_setup import get_logger, setup_logging
from .app import build_dispatcher, create_bot

log = get_logger(__name__)


async def _run() -> None:
    setup_logging()
    settings = Settings.from_env()
    settings.require_bot()

    engine = make_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)
    bot = create_bot(settings.telegram_bot_token)
    dp = build_dispatcher(sessionmaker, settings.bot_allowed_user_ids)

    log.info("Бот стартует в polling-режиме (доступ: %d id)", len(settings.bot_allowed_user_ids))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
