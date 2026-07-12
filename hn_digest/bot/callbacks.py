"""Фабрики callback-данных (aiogram). Все сериализации укладываются в лимит 64 байта.

Карточка поста всюду адресуется тройкой (d=дата ISO, i=индекс в дне, s=источник),
где источник 'd' — переход из списка дат, 's' — из сохранённых. Пост по (d, i)
всегда однозначно находится через repo.get_posts_for_date(d)[i].
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData

# Источник карточки — куда ведёт кнопка «назад».
SRC_DATES = "d"
SRC_SAVED = "s"


class MenuCb(CallbackData, prefix="m"):
    action: str  # latest | dates | saved | home | noop


class DatesCb(CallbackData, prefix="dts"):
    page: int  # страница списка дат


class DatePickCb(CallbackData, prefix="dp"):
    d: str  # ISO-дата выпуска


class CardCb(CallbackData, prefix="c"):
    d: str  # ISO-дата
    i: int  # индекс поста в дне
    s: str  # источник (SRC_DATES / SRC_SAVED)


class SaveCb(CallbackData, prefix="sv"):
    d: str
    i: int
    s: str


class SavedCb(CallbackData, prefix="svd"):
    page: int  # страница списка сохранённых


class SavedOpenCb(CallbackData, prefix="so"):
    pid: int  # post_id открываемого сохранённого поста
