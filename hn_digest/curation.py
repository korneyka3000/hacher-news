"""Курация кандидатов через Claude Code CLI (`claude -p`)."""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

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
    # --output-format json даёт конверт с текстом ответа + usage/цена прогона.
    cmd = [settings.claude_bin, "-p", CURATION_PROMPT, "--output-format", "json"]
    if settings.claude_model:
        cmd += ["--model", settings.claude_model]

    log.info("Запуск курации: %s -p (кандидатов: %s)", settings.claude_bin, len(candidates))
    try:
        proc = subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        raise SystemExit(
            f"Не найден бинарь Claude Code: '{settings.claude_bin}'. "
            "Установи Claude Code или задай CLAUDE_BIN в .env (полный путь к claude)."
        ) from None
    except subprocess.TimeoutExpired:
        raise SystemExit("Курация claude -p не уложилась в тайм-аут (300с).") from None

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip() or (proc.stdout or "").strip() or "(пустой вывод)"
        raise SystemExit(f"claude -p завершился с ошибкой {proc.returncode}:\n{detail}")

    text, usage, cost, duration = _parse_envelope(proc.stdout)
    selected = _extract_json_array(text)
    by_id = {s.id: s for s in candidates}
    items = [CuratedItem.from_claude(raw, by_id.get(str(raw.get("id", "")))) for raw in selected]
    items = [it for it in items if it.title_ru]  # отсекаем пустышки

    cost_str = f"${cost:.4f}" if isinstance(cost, (int, float)) else "—"
    log.info(
        "Курация: %s кандидатов → %s выбрано; токены in=%s out=%s; цена %s",
        len(candidates),
        len(items),
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        cost_str,
    )
    _record_usage(
        settings.usage_path,
        candidates=len(candidates),
        selected=len(items),
        usage=usage,
        cost=cost,
        duration=duration,
    )
    return items


def _parse_envelope(stdout: str) -> tuple[str, dict, float | None, int | None]:
    """Разбирает конверт `claude --output-format json`.

    Возвращает (текст_ответа, usage, cost_usd, duration_ms). Если вывод не JSON
    (старый CLI / текстовый режим) — трактует stdout как сырой ответ, usage пуст.
    """
    try:
        env = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout, {}, None, None
    if not isinstance(env, dict):
        return stdout, {}, None, None
    text = env.get("result", "")
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False)
    usage = env.get("usage") if isinstance(env.get("usage"), dict) else {}
    cost = env.get("total_cost_usd")
    duration = env.get("duration_ms")
    return text, usage, cost, duration


def _record_usage(
    path: Path,
    *,
    candidates: int,
    selected: int,
    usage: dict,
    cost: float | None,
    duration: int | None,
) -> None:
    """Дописывает строку расхода токенов/цены в JSONL-леджер (best-effort)."""
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "candidates": candidates,
        "selected": selected,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "cost_usd": cost,
        "duration_ms": duration,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("Не удалось записать usage-леджер %s: %s", path, exc)


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
