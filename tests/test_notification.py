"""Тесты билдера уведомления о новом выпуске (чистая функция)."""

from __future__ import annotations

from datetime import date

from hn_digest.formatting import build_notification
from hn_digest.models import CuratedItem


def _items(n: int) -> list[CuratedItem]:
    return [
        CuratedItem(id=str(i), title_ru=f"Заголовок {i}", summary="", verdict="", why="", tag="")
        for i in range(n)
    ]


def test_notification_text_and_button():
    text, markup = build_notification(date(2026, 7, 12), _items(5), "MyBot")
    assert "12.07.2026" in text
    assert "Отобрано историй: 5" in text
    assert "Заголовок 0" in text
    assert "…и ещё 2" in text  # 5 - 3 в тизере
    btn = markup["inline_keyboard"][0][0]
    assert btn["url"] == "https://t.me/MyBot?start=latest"
    assert "Открыть" in btn["text"]


def test_notification_no_more_line_when_few():
    text, _ = build_notification(date(2026, 7, 12), _items(2), "B")
    assert "…и ещё" not in text


def test_notification_escapes_html():
    items = [CuratedItem(id="1", title_ru="a <b> & c", summary="", verdict="", why="", tag="")]
    text, _ = build_notification(date(2026, 1, 1), items, "B")
    assert "&lt;b&gt;" in text
    assert "&amp;" in text
