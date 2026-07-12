"""Тесты чистого рендеринга карточки и подписей (без БД/сети)."""

from __future__ import annotations

from datetime import date

from hn_digest.bot.render import (
    date_button_label,
    fmt_date,
    fmt_date_short,
    render_card,
    saved_button_label,
)
from hn_digest.db.models import Post


def make_post(**kw) -> Post:
    defaults = {
        "hn_id": "x",
        "digest_date": date(2026, 7, 12),
        "title_ru": "Заголовок",
        "summary": "Краткое содержание",
        "verdict": "🟢 Полезно",
        "why": "почему стоит",
        "tag": "🤖 AI",
        "url": "http://u",
        "hn_url": "http://hn",
        "points": 42,
        "num_comments": 7,
        "position": 0,
    }
    defaults.update(kw)
    return Post(**defaults)


def test_render_card_has_position_and_new_badge():
    txt = render_card(make_post(), idx=2, total=12, is_new=True)
    assert "3/12" in txt
    assert "🆕" in txt
    assert "<b>Заголовок</b>" in txt
    assert "🤖" in txt  # ведущий эмодзи тега
    assert "👍 42" in txt and "💬 7" in txt


def test_render_card_no_new_badge_when_viewed():
    assert "🆕" not in render_card(make_post(), idx=0, total=5, is_new=False)


def test_render_card_escapes_html():
    txt = render_card(make_post(title_ru="a <b> & c"), idx=0, total=1, is_new=False)
    assert "&lt;b&gt;" in txt
    assert "&amp;" in txt


def test_render_card_omits_empty_optional_fields():
    txt = render_card(make_post(summary="", why="", verdict=""), idx=0, total=1, is_new=False)
    assert "<blockquote>" not in txt
    assert "💡" not in txt
    assert "Вердикт" not in txt


def test_fmt_date():
    assert fmt_date(date(2026, 1, 5)) == "5 янв 2026"
    assert fmt_date_short(date(2026, 12, 31)) == "31 дек"


def test_date_button_label_badges():
    assert date_button_label(date(2026, 7, 12), 12, 3).endswith("🆕 3")
    assert date_button_label(date(2026, 7, 12), 12, 0).endswith("✓")


def test_saved_button_label_truncates():
    lbl = saved_button_label(make_post(title_ru="д" * 60))
    assert lbl.startswith("⭐")
    assert "…" in lbl
    assert len(lbl) < 60
