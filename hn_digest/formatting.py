"""Сборка Telegram-сообщений (HTML) из отобранных историй."""

from __future__ import annotations

import html
from datetime import datetime

from .models import CuratedItem

TELEGRAM_LIMIT = 4096
SAFE_CHUNK = 3900  # с запасом под лимит Telegram


def build_messages(items: list[CuratedItem]) -> list[str]:
    """Формирует список сообщений, каждое ≤ лимита Telegram."""
    today = datetime.now().strftime("%d.%m.%Y")
    header = f"🗞 <b>HN дайджест — {today}</b>\nОтобрано стоящего: {len(items)}\n"

    blocks: list[str] = [header]
    for i, it in enumerate(items, 1):
        blocks.append(_format_item(i, it))

    if not items:
        blocks.append("Сегодня ничего нового и стоящего не нашлось — бывает. Завтра новый заход. 🙂")

    return _pack(blocks)


def _format_item(index: int, it: CuratedItem) -> str:
    title = html.escape(it.title_ru)
    parts = [f"{index}. {html.escape(it.tag)}  <b>{title}</b>"]
    if it.summary:
        parts.append(html.escape(it.summary))
    meta = " · ".join(x for x in (it.verdict, it.why) if x)
    if meta:
        parts.append(f"<i>{html.escape(meta)}</i>")
    parts.append(
        f'🔗 <a href="{html.escape(it.url)}">Ссылка</a> · '
        f'<a href="{html.escape(it.hn_url)}">HN ({it.points}▲ / {it.num_comments}💬)</a>'
    )
    return "\n".join(parts)


def _pack(blocks: list[str]) -> list[str]:
    """Склеивает блоки в сообщения, не превышая лимит."""
    messages: list[str] = []
    current = ""
    for block in blocks:
        candidate = block if not current else current + "\n\n" + block
        if len(candidate) > SAFE_CHUNK and current:
            messages.append(current)
            current = block
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages
