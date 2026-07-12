"""Форматирование карточки поста и подписей (HTML для Telegram)."""

from __future__ import annotations

import html
from datetime import date

from ..db.models import Post

_MONTHS_RU = (
    "янв",
    "фев",
    "мар",
    "апр",
    "май",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
)


def fmt_date(d: date) -> str:
    """`2026-07-12` → `12 июл 2026`."""
    return f"{d.day} {_MONTHS_RU[d.month - 1]} {d.year}"


def fmt_date_short(d: date) -> str:
    """`2026-07-12` → `12 июл`."""
    return f"{d.day} {_MONTHS_RU[d.month - 1]}"


def _lead_emoji(s: str) -> str:
    """Ведущий эмодзи из строки вида '🤖 AI' → '🤖' (пусто, если нет)."""
    s = s.strip()
    return s.split(" ", 1)[0] if s else ""


def _esc(s: str) -> str:
    """Схлопывает пробелы и экранирует HTML."""
    return html.escape(" ".join(s.split()))


def render_card(post: Post, idx: int, total: int, is_new: bool) -> str:
    """HTML-текст карточки поста для одного сообщения."""
    head_bits = [
        f"📅 {fmt_date_short(post.digest_date)}",
        f"{idx + 1}/{total}",
    ]
    tag_emoji = _lead_emoji(post.tag)
    if tag_emoji:
        head_bits.append(tag_emoji)
    if is_new:
        head_bits.append("🆕")
    parts = [" · ".join(head_bits), f"<b>{_esc(post.title_ru)}</b>"]
    if post.summary:
        parts.append(f"<blockquote>{_esc(post.summary)}</blockquote>")
    if post.why:
        parts.append(f"💡 {_esc(post.why)}")
    if post.verdict:
        parts.append(f"Вердикт: {_esc(post.verdict)}")
    parts.append(f"👍 {post.points} · 💬 {post.num_comments}")
    return "\n".join(parts)


def saved_button_label(post: Post) -> str:
    """Короткая подпись поста в списке сохранённых."""
    title = post.title_ru.strip() or post.hn_id
    if len(title) > 40:
        title = title[:39].rstrip() + "…"
    return f"⭐ {title} · {fmt_date_short(post.digest_date)}"


def date_button_label(d: date, total: int, unviewed: int) -> str:
    """Подпись дня в списке дат: с бейджем непросмотренного либо галочкой."""
    badge = f"🆕 {unviewed}" if unviewed else "✓"
    return f"{fmt_date(d)} · {total} · {badge}"
