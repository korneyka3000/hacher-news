"""Юнит-тесты чистой логики (без сети, claude и Telegram).

Запуск: `uv run pytest`
"""

from __future__ import annotations

import json
from pathlib import Path

from hn_digest.curation import _extract_json_array
from hn_digest.dedup import SeenStore
from hn_digest.formatting import build_messages
from hn_digest.models import CuratedItem, Story


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
    raw = {"id": str(i), "title_ru": f"История {i}", "summary": "s",
           "verdict": "🟢 Полезно", "why": "w", "tag": "🚀 Стартап"}
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


def test_html_is_escaped():
    msgs = build_messages([mk_item(1, title_ru="A & B <script>", summary="1<2")])
    assert "&amp;" in msgs[0]
    assert "&lt;script&gt;" in msgs[0]


def test_empty_digest_has_friendly_note():
    assert "ничего нового" in build_messages([])[0]
