"""Билдеры inline-клавиатур."""

from __future__ import annotations

from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..db.models import Post
from .callbacks import (
    SRC_DATES,
    SRC_SAVED,
    CardCb,
    DatePickCb,
    DatesCb,
    MenuCb,
    SaveCb,
    SavedCb,
    SavedOpenCb,
)
from .render import date_button_label, saved_button_label

PAGE_DATES = 8  # дней на страницу
PAGE_SAVED = 8  # сохранённых на страницу

_HOME = InlineKeyboardButton(text="🏠 Меню", callback_data=MenuCb(action="home").pack())


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⚡ Latest", callback_data=MenuCb(action="latest"))
    kb.button(text="📅 По датам", callback_data=MenuCb(action="dates"))
    kb.button(text="⭐ Мои сохранённые", callback_data=MenuCb(action="saved"))
    kb.adjust(1)
    return kb.as_markup()


def dates_kb(rows: list[tuple[date, int, int]], page: int, has_next: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d, total, unviewed in rows:
        kb.button(
            text=date_button_label(d, total, unviewed),
            callback_data=DatePickCb(d=d.isoformat()),
        )
    kb.adjust(1)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="⬅️ Новее", callback_data=DatesCb(page=page - 1).pack())
        )
    if has_next:
        nav.append(
            InlineKeyboardButton(text="Раньше ➡️", callback_data=DatesCb(page=page + 1).pack())
        )
    if nav:
        kb.row(*nav)
    kb.row(_HOME)
    return kb.as_markup()


def card_kb(
    post: Post, d: str, idx: int, src: str, total: int, is_saved: bool
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    links: list[InlineKeyboardButton] = []
    if post.url:
        links.append(InlineKeyboardButton(text="🔗 Читать", url=post.url))
    if post.hn_url:
        links.append(InlineKeyboardButton(text="💬 HN", url=post.hn_url))
    if links:
        kb.row(*links)

    left = CardCb(d=d, i=idx - 1, s=src) if idx > 0 else MenuCb(action="noop")
    right = CardCb(d=d, i=idx + 1, s=src) if idx < total - 1 else MenuCb(action="noop")
    kb.row(
        InlineKeyboardButton(text="⬅️", callback_data=left.pack()),
        InlineKeyboardButton(text=f"{idx + 1}/{total}", callback_data=MenuCb(action="noop").pack()),
        InlineKeyboardButton(text="➡️", callback_data=right.pack()),
    )

    kb.row(
        InlineKeyboardButton(
            text="✅ Сохранено" if is_saved else "⭐ Сохранить",
            callback_data=SaveCb(d=d, i=idx, s=src).pack(),
        )
    )

    if src == SRC_SAVED:
        back = InlineKeyboardButton(text="⭐ К сохранённым", callback_data=SavedCb(page=0).pack())
    else:
        back = InlineKeyboardButton(text="🗓 К датам", callback_data=DatesCb(page=0).pack())
    kb.row(back, _HOME)
    return kb.as_markup()


def saved_kb(posts: list[Post], page: int, has_next: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in posts:
        kb.button(text=saved_button_label(p), callback_data=SavedOpenCb(pid=p.id))
    kb.adjust(1)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=SavedCb(page=page - 1).pack()))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=SavedCb(page=page + 1).pack()))
    if nav:
        kb.row(*nav)
    kb.row(_HOME)
    return kb.as_markup()


# Мелкая деталь: SRC_DATES импортируется, чтобы хендлеры брали константу отсюда же.
__all__ = [
    "PAGE_DATES",
    "PAGE_SAVED",
    "SRC_DATES",
    "SRC_SAVED",
    "card_kb",
    "dates_kb",
    "main_menu",
    "saved_kb",
]
