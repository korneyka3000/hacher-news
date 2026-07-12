"""Тесты сериализации callback-данных: round-trip и лимит Telegram (64 байта)."""

from __future__ import annotations

from hn_digest.bot.callbacks import (
    CardCb,
    DatePickCb,
    DatesCb,
    MenuCb,
    SaveCb,
    SavedCb,
    SavedOpenCb,
)


def test_card_roundtrip():
    packed = CardCb(d="2026-07-12", i=5, s="d").pack()
    back = CardCb.unpack(packed)
    assert (back.d, back.i, back.s) == ("2026-07-12", 5, "d")


def test_all_callbacks_within_limit():
    samples = [
        CardCb(d="2026-12-31", i=999, s="s"),
        SaveCb(d="2026-12-31", i=999, s="s"),
        DatesCb(page=99),
        DatePickCb(d="2026-12-31"),
        MenuCb(action="latest"),
        SavedCb(page=99),
        SavedOpenCb(pid=9223372036854775807),  # max BIGINT
    ]
    for cb in samples:
        assert len(cb.pack().encode()) <= 64, cb
