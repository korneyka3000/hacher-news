"""Юнит-тесты чистой логики (без сети, claude и Telegram).

Запуск: `uv run pytest`
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from hn_digest.curation import _extract_json_array, _parse_envelope, _record_usage
from hn_digest.dedup import SeenStore
from hn_digest.formatting import SEP, build_messages
from hn_digest.models import CuratedItem, Story
from hn_digest.scheduling import is_within_window
from hn_digest.sources import _clean_text, _extract_meta_context


def mk_story(i: int) -> Story:
    return Story(
        id=str(i),
        title=f"S{i}",
        url=f"https://e.com/{i}",
        hn_url=f"https://news.ycombinator.com/item?id={i}",
        points=100 + i,
        num_comments=i,
        author="a",
        is_show_hn=False,
        text="",
    )


def mk_item(i: int, **over) -> CuratedItem:
    raw = {
        "id": str(i),
        "title_ru": f"История {i}",
        "summary": "s",
        "verdict": "🟢 Полезно",
        "why": "w",
        "tag": "🚀 Стартап",
    }
    raw.update(over)
    return CuratedItem.from_claude(raw, mk_story(i))


# --------------------------------------------------------------------------- #
# dedup
# --------------------------------------------------------------------------- #


def test_dedup_filters_sent_and_persists(tmp_path: Path):
    p = tmp_path / "seen.json"
    store = SeenStore(p, ttl_days=30)
    stories = [mk_story(i) for i in range(5)]
    assert len(store.filter_new(stories)) == 5

    store.mark_sent([mk_item(i) for i in range(3)])
    assert p.exists()

    # новый инстанс читает состояние с диска
    reloaded = SeenStore(p, ttl_days=30)
    fresh_ids = {s.id for s in reloaded.filter_new(stories)}
    assert fresh_ids == {"3", "4"}


def test_dedup_ttl_prune(tmp_path: Path):
    p = tmp_path / "seen.json"
    p.write_text(json.dumps({"999": 0.0}))  # запись из эпохи Unix — заведомо протухла
    store = SeenStore(p, ttl_days=30)
    store.mark_sent([])  # триггерит prune + save
    assert "999" not in json.loads(p.read_text())


def test_dry_run_does_not_mark(tmp_path: Path):
    # mark_sent НЕ вызывается в dry-run — проверяем на уровне контракта store:
    p = tmp_path / "seen.json"
    store = SeenStore(p, ttl_days=30)
    store.filter_new([mk_story(1)])  # только чтение
    assert not p.exists(), "чтение не должно создавать файл состояния"


# --------------------------------------------------------------------------- #
# curation (парсинг ответа модели)
# --------------------------------------------------------------------------- #


def test_extract_json_from_fences():
    raw = '```json\n[{"id":"1","title_ru":"X"}]\n```'
    parsed = _extract_json_array(raw)
    assert parsed == [{"id": "1", "title_ru": "X"}]


def test_extract_json_embedded_in_text():
    raw = 'Вот результат: [{"id":"2"}] надеюсь помог'
    assert _extract_json_array(raw) == [{"id": "2"}]


def test_extract_json_garbage_returns_empty():
    assert _extract_json_array("совсем не json") == []


def test_curated_item_enriched_from_story():
    ci = mk_item(7)
    assert ci.points == 107
    assert ci.hn_url.endswith("id=7")


# --------------------------------------------------------------------------- #
# formatting
# --------------------------------------------------------------------------- #


def test_messages_respect_telegram_limit():
    items = [mk_item(i, summary="Описание " * 12) for i in range(60)]
    msgs = build_messages(items)
    assert len(msgs) >= 2
    assert all(len(m) <= 4096 for m in msgs)


def test_large_digest_splits_without_breaking_html():
    # Много историй → несколько сообщений; в каждом теги <blockquote>/<b>
    # сбалансированы (разрез не рвёт разметку) и лимит соблюдён.
    items = [mk_item(i, summary="Описание технологии. " * 20) for i in range(80)]
    msgs = build_messages(items)
    assert len(msgs) >= 2
    for m in msgs:
        assert len(m) <= 4096
        assert m.count("<blockquote>") == m.count("</blockquote>")
        assert m.count("<b>") == m.count("</b>")


def test_summary_newlines_collapsed_to_single_line():
    # Переносы в summary схлопываются — blockquote остаётся одной строкой.
    msg = build_messages([mk_item(1, summary="Первая строка.\n\nВторая строка.")])[0]
    assert "<blockquote>Первая строка. Вторая строка.</blockquote>" in msg


def test_html_is_escaped():
    msgs = build_messages([mk_item(1, title_ru="A & B <script>", summary="1<2")])
    assert "&amp;" in msgs[0]
    assert "&lt;script&gt;" in msgs[0]


def test_empty_digest_has_friendly_note():
    assert "ничего нового" in build_messages([])[0]


def test_item_has_badge_blockquote_and_separator():
    msg = build_messages([mk_item(1)])[0]
    assert "🟢" in msg  # бейдж вердикта
    assert "🚀" in msg  # иконка тега
    assert "<blockquote>" in msg  # описание в цитате
    assert SEP in msg  # разделитель
    assert "▲" in msg and "💬" in msg  # строка метрик


def test_emoji_only_no_verdict_word():
    # Слово вердикта («Полезно») в заголовок не попадает — только эмодзи-бейдж.
    msg = build_messages([mk_item(1, title_ru="Заголовок")])[0]
    assert "🟢 1. 🚀 <b>Заголовок</b>" in msg


# --------------------------------------------------------------------------- #
# sources: чистка текста + мета-контекст (без сети)
# --------------------------------------------------------------------------- #


def test_clean_text_unescapes_and_collapses():
    raw = "Foo &amp; bar <p>baz</p>\n\n  qux&#x27;s"
    assert _clean_text(raw, 100) == "Foo & bar baz qux's"


def test_clean_text_truncates_on_sentence_boundary():
    raw = "Первое довольно длинное предложение тут. И ещё что-то потом идёт дальше"
    out = _clean_text(raw, 45)
    assert out == "Первое довольно длинное предложение тут."  # обрезали по концу предложения


def test_clean_text_word_boundary_with_ellipsis():
    raw = "одно " * 50
    out = _clean_text(raw.strip(), 20)
    assert out.endswith("…") and len(out) <= 21 and " одно" not in out[-2:]


def test_extract_meta_context_prefers_longest_description():
    page = """
    <html><head>
      <meta name="viewport" content="width=device-width">
      <meta content="Короткое" name="description">
      <meta property="og:description" content="Более длинное и содержательное описание статьи.">
    </head></html>
    """
    assert _extract_meta_context(page) == "Более длинное и содержательное описание статьи."


def test_extract_meta_context_empty_when_no_description():
    assert _extract_meta_context("<html><head><title>X</title></head></html>") == ""


# --------------------------------------------------------------------------- #
# scheduling (гард окна запуска)
# --------------------------------------------------------------------------- #


def test_within_window_at_target():
    now = datetime(2026, 7, 10, 9, 0)
    assert is_within_window(now, 9, 0, 90) is True


def test_within_window_before_target():
    now = datetime(2026, 7, 10, 7, 30)  # раньше цели — ручной ранний прогон ок
    assert is_within_window(now, 9, 0, 90) is True


def test_within_window_inside_edge():
    now = datetime(2026, 7, 10, 10, 30)  # ровно 9:00 + 90 мин
    assert is_within_window(now, 9, 0, 90) is True


def test_outside_window_late_wake():
    now = datetime(2026, 7, 10, 15, 0)  # проснулись днём — пропуск
    assert is_within_window(now, 9, 0, 90) is False


# --------------------------------------------------------------------------- #
# curation: конверт --output-format json + леджер usage
# --------------------------------------------------------------------------- #


def test_parse_envelope_extracts_result_and_usage():
    envelope = json.dumps(
        {
            "result": '[{"id":"1","title_ru":"X"}]',
            "usage": {"input_tokens": 120, "output_tokens": 30},
            "total_cost_usd": 0.0123,
            "duration_ms": 4567,
        }
    )
    text, usage, cost, duration = _parse_envelope(envelope)
    assert _extract_json_array(text) == [{"id": "1", "title_ru": "X"}]
    assert usage["input_tokens"] == 120
    assert cost == 0.0123
    assert duration == 4567


def test_parse_envelope_falls_back_on_raw_text():
    # Старый CLI / текстовый режим: не-конверт трактуется как сырой ответ.
    text, usage, cost, duration = _parse_envelope('[{"id":"2"}]')
    assert _extract_json_array(text) == [{"id": "2"}]
    assert usage == {} and cost is None and duration is None

    text2, usage2, _, _ = _parse_envelope("совсем не json")
    assert text2 == "совсем не json" and usage2 == {}


def test_record_usage_appends_jsonl(tmp_path: Path):
    p = tmp_path / "usage.jsonl"
    _record_usage(
        p,
        candidates=5,
        selected=2,
        usage={"input_tokens": 100, "output_tokens": 20},
        cost=0.01,
        duration=999,
    )
    _record_usage(p, candidates=3, selected=0, usage={}, cost=None, duration=None)
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["candidates"] == 5 and first["selected"] == 2
    assert first["input_tokens"] == 100 and first["cost_usd"] == 0.01
    assert "ts" in first
