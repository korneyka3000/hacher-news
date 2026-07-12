"""Точка деплоя на FastAPI Cloud: FastAPI + aiogram в webhook-режиме.

Импорт модуля безопасен без env (движок/бот создаются в lifespan), поэтому
детект приложения и сборка на FastAPI Cloud не падают. Аутентичность апдейта
проверяется по заголовку `X-Telegram-Bot-Api-Secret-Token`, путь фиксированный.

Локальная проверка: `uvicorn hn_digest.bot.main:app` (нужны env, см. .env).
Прод: `fastapi deploy` (ASGI-приложение `app`).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request

from ..config import Settings
from ..db import make_engine, make_sessionmaker
from ..logging_setup import get_logger, setup_logging
from .app import build_dispatcher, create_bot

log = get_logger(__name__)

WEBHOOK_PATH = "/tg/webhook"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = Settings.from_env()
    settings.require_bot()
    if not settings.webhook_secret:
        raise SystemExit("Не задан WEBHOOK_SECRET (см. .env) — webhook небезопасен.")

    engine = make_engine(settings.database_url)
    bot = create_bot(settings.telegram_bot_token)
    dp = build_dispatcher(make_sessionmaker(engine), settings.bot_allowed_user_ids)
    app.state.bot = bot
    app.state.dp = dp
    app.state.secret = settings.webhook_secret

    if settings.webhook_base_url:
        url = f"{settings.webhook_base_url}{WEBHOOK_PATH}"
        await bot.set_webhook(
            url,
            secret_token=settings.webhook_secret,
            drop_pending_updates=True,
            allowed_updates=dp.resolve_used_update_types(),
        )
        log.info("Webhook установлен: %s", url)
    else:
        log.warning(
            "WEBHOOK_BASE_URL не задан — webhook не установлен. "
            "Задай его в env и передеплой (или вызови set_webhook вручную)."
        )
    try:
        yield
    finally:
        await bot.session.close()
        await engine.dispose()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post(WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if x_telegram_bot_api_secret_token != request.app.state.secret:
        raise HTTPException(status_code=403, detail="bad secret token")
    bot = request.app.state.bot
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await request.app.state.dp.feed_update(bot, update)
    # Всегда 200 — иначе Telegram будет ретраить доставку.
    return {"ok": True}
