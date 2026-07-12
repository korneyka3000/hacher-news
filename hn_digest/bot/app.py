"""Сборка Bot и Dispatcher (общая для webhook-прода и polling-разработки)."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .access import AccessMiddleware, DbSessionMiddleware
from .handlers import router


def create_bot(token: str) -> Bot:
    return Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def build_dispatcher(
    sessionmaker: async_sessionmaker[AsyncSession], allowed_ids: frozenset[int]
) -> Dispatcher:
    dp = Dispatcher()
    # Порядок важен: сперва проверка доступа, потом выдача сессии.
    for observer in (dp.message, dp.callback_query):
        observer.middleware(AccessMiddleware(allowed_ids))
        observer.middleware(DbSessionMiddleware(sessionmaker))
    dp.include_router(router)
    return dp
