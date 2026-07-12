"""Middleware: проверка whitelist и выдача AsyncSession в хендлеры."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class AccessMiddleware(BaseMiddleware):
    """Пропускает только пользователей из whitelist; остальным — вежливый отказ."""

    def __init__(self, allowed_ids: frozenset[int]) -> None:
        self._allowed = allowed_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None or user.id not in self._allowed:
            await self._deny(event)
            return None
        return await handler(event, data)

    @staticmethod
    async def _deny(event: TelegramObject) -> None:
        if isinstance(event, CallbackQuery):
            await event.answer("Нет доступа.", show_alert=True)
        elif isinstance(event, Message):
            await event.answer("Нет доступа к этому боту.")


class DbSessionMiddleware(BaseMiddleware):
    """Открывает сессию на время обработки апдейта и коммитит по успеху."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._sessionmaker() as session:
            data["session"] = session
            result = await handler(event, data)
            await session.commit()
            return result
