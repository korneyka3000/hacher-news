"""Сборка Telegram-сообщений (HTML) из отобранных историй."""

from __future__ import annotations

import html
from datetime import datetime

from .models import CuratedItem

TELEGRAM_LIMIT = 4096
SAFE_CHUNK = 3900  # с запасом под лимит Telegram
SEP = "────────────"  # разделитель между историями
EMPTY_NOTE = "Сегодня ничего нового и стоящего не нашлось — бывает. Завтра новый заход. 🙂"


def build_messages(items: list[CuratedItem]) -> list[str]:
    """Формирует список сообщений, каждое ≤ лимита Telegram."""
    today = datetime.now().strftime("%d.%m.%Y")
    header = f"🗞 <b>HN дайджест — {today}</b>\nОтобрано: {len(items)}"

    blocks: list[str] = [header]
    for i, it in enumerate(items, 1):
        blocks.append(f"{SEP}\n{_format_item(i, it)}")

    if not items:
        blocks.append(EMPTY_NOTE)

    return _pack(blocks)


def _format_item(index: int, it: CuratedItem) -> str:
    # Заголовок: бейдж вердикта (цвет) · номер · иконка тега · название.
    head = " ".join(x for x in (_emoji(it.verdict), f"{index}.", _emoji(it.tag)) if x)
    parts = [f"{head} <b>{_esc(it.title_ru)}</b>"]
    if it.summary:
        parts.append(f"<blockquote>{_esc(it.summary)}</blockquote>")
    if it.why:
        parts.append(f"💡 {_esc(it.why)}")
    parts.append(
        f"{it.points}▲ · {it.num_comments}💬 · "
        f'<a href="{html.escape(it.url)}">Ссылка</a> · '
        f'<a href="{html.escape(it.hn_url)}">HN</a>'
    )
    return "\n".join(parts)


def _esc(s: str) -> str:
    """Схлопывает пробелы/переносы в одну строку и экранирует HTML.

    Однострочность важна для `_fit`: каждый HTML-элемент остаётся на своей
    строке, поэтому разрез длинного блока по '\\n' не рвёт теги.
    """
    return html.escape(" ".join(s.split()))


def _emoji(s: str) -> str:
    """Достаёт ведущий эмодзи из строки вида '🟢 Полезно' → '🟢'."""
    s = s.strip()
    return s.split(" ", 1)[0] if s else ""


def _pack(blocks: list[str]) -> list[str]:
    """Склеивает блоки в сообщения, не превышая лимит.

    Блоки, которые сами по себе длиннее лимита (одна очень длинная история),
    предварительно режутся `_fit` по строкам — так одно сообщение никогда не
    превысит лимит Telegram.
    """
    messages: list[str] = []
    current = ""
    for block in blocks:
        for piece in _fit(block):
            candidate = piece if not current else current + "\n\n" + piece
            if len(candidate) > SAFE_CHUNK and current:
                messages.append(current)
                current = piece
            else:
                current = candidate
    if current:
        messages.append(current)
    return messages


def _fit(block: str) -> list[str]:
    """Режет слишком длинный блок на куски ≤ SAFE_CHUNK по границам строк.

    Каждый HTML-элемент (заголовок, <blockquote>, ссылки) занимает отдельную
    строку и закрывается на ней же, поэтому разрез по '\\n' не ломает разметку.
    """
    if len(block) <= SAFE_CHUNK:
        return [block]
    chunks: list[str] = []
    current = ""
    for line in block.split("\n"):
        candidate = line if not current else current + "\n" + line
        if len(candidate) > SAFE_CHUNK and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
