"""Тесты whitelist-middleware и парсинга списка доступа."""

from __future__ import annotations

from typing import cast

from aiogram.types import TelegramObject

from hn_digest.bot.access import AccessMiddleware
from hn_digest.config import _parse_ids

# Middleware трогает только data["event_from_user"], поэтому событие может быть
# любым объектом — приводим типом, чтобы удовлетворить статическую проверку.
_EVENT = cast(TelegramObject, object())


class _FakeUser:
    def __init__(self, uid: int) -> None:
        self.id = uid


def test_parse_ids_variants():
    assert _parse_ids("111, 222 ;333") == frozenset({111, 222, 333})
    assert _parse_ids("") == frozenset()
    assert _parse_ids("abc, 12, -5, ") == frozenset({12, -5})


async def test_access_allows_whitelisted():
    mw = AccessMiddleware(frozenset({1, 2}))
    called: dict[str, bool] = {}

    async def handler(event, data):
        called["ran"] = True
        return "RESULT"

    result = await mw(handler, _EVENT, {"event_from_user": _FakeUser(1)})
    assert result == "RESULT"
    assert called.get("ran")


async def test_access_blocks_outsider():
    mw = AccessMiddleware(frozenset({1, 2}))
    called: dict[str, bool] = {}

    async def handler(event, data):
        called["ran"] = True

    # Плоский object() — не Message/CallbackQuery, поэтому _deny просто no-op.
    result = await mw(handler, _EVENT, {"event_from_user": _FakeUser(999)})
    assert result is None
    assert "ran" not in called


async def test_access_blocks_when_no_user():
    mw = AccessMiddleware(frozenset({1}))
    called: dict[str, bool] = {}

    async def handler(event, data):
        called["ran"] = True

    result = await mw(handler, _EVENT, {"event_from_user": None})
    assert result is None
    assert "ran" not in called
