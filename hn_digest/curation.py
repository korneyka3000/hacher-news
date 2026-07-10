"""Курация кандидатов через Claude Code CLI (`claude -p`)."""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess

from .config import Settings
from .logging_setup import get_logger
from .models import CuratedItem, Story

log = get_logger(__name__)

CURATION_PROMPT = """\
Ты — редактор технологического дайджеста для IT-инженера. Тебе дан список историй \
с Hacker News (JSON). Отбери ТОЛЬКО действительно стоящее: новые стартапы и их запуски, \
свежие идеи и подходы, крутые технические фичи и инструменты, значимые релизы. \
Отбрасывай: драму, политику, мета-обсуждения HN, кликбейт, вкусовщину без сути, \
дубликаты по смыслу.

Не ограничивай себя фиксированным числом — если стоящего много, включи всё стоящее; \
если мало, включи мало. Лучше меньше, да лучше.

Для каждой выбранной истории верни объект с полями:
  - "title_ru": короткий заголовок на русском (названия продуктов можно латиницей),
  - "summary": 1–3 предложения по-русски: что это и почему интересно,
  - "verdict": строго одно из "🟢 Полезно", "🟡 На заметку", "🔴 Мимо",
  - "why": 1 предложение — кому и чем полезно,
  - "tag": одно из "🚀 Стартап", "💡 Идея", "🛠 Инструмент", "✨ Фича", "📦 Релиз", "📚 Материал",
  - "id": объект id истории из входных данных (строкой).

Верни СТРОГО валидный JSON-массив таких объектов и НИЧЕГО больше — без markdown, без пояснений. \
Если ничего стоящего нет — верни [].
"""


def curate(candidates: list[Story], settings: Settings) -> list[CuratedItem]:
    """Прогоняет кандидатов через claude -p и возвращает отобранные элементы."""
    if not candidates:
        return []

    payload = json.dumps([dataclasses.asdict(s) for s in candidates], ensure_ascii=False)
    cmd = [settings.claude_bin, "-p", CURATION_PROMPT]
    if settings.claude_model:
        cmd += ["--model", settings.claude_model]

    log.info("Запуск курации: %s -p (кандидатов: %s)", settings.claude_bin, len(candidates))
    try:
        proc = subprocess.run(
            cmd, input=payload, capture_output=True, text=True, timeout=300
        )
    except FileNotFoundError:
        raise SystemExit(
            f"Не найден бинарь Claude Code: '{settings.claude_bin}'. "
            "Установи Claude Code или задай CLAUDE_BIN в .env (полный путь к claude)."
        )
    except subprocess.TimeoutExpired:
        raise SystemExit("Курация claude -p не уложилась в тайм-аут (300с).")

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip() or (proc.stdout or "").strip() or "(пустой вывод)"
        raise SystemExit(f"claude -p завершился с ошибкой {proc.returncode}:\n{detail}")

    selected = _extract_json_array(proc.stdout)
    by_id = {s.id: s for s in candidates}
    items = [CuratedItem.from_claude(raw, by_id.get(str(raw.get("id", "")))) for raw in selected]
    items = [it for it in items if it.title_ru]  # отсекаем пустышки
    log.info("Claude отобрал: %s", len(items))
    return items


def _extract_json_array(raw: str) -> list[dict]:
    """Достаёт JSON-массив из вывода модели (на случай обёрток/фенсов)."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    log.error("Не удалось распарсить JSON от Claude. Сырой вывод:\n%s", raw[:1000])
    return []
