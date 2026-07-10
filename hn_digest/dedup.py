"""Антидубли: помним, какие истории уже отправляли, и не шлём их снова."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .logging_setup import get_logger
from .models import CuratedItem, Story

log = get_logger(__name__)


class SeenStore:
    """Простое персистентное хранилище id отправленных историй (JSON: id -> unix ts)."""

    def __init__(self, path: Path, ttl_days: int = 30) -> None:
        self.path = path
        self.ttl_seconds = ttl_days * 86400
        self._seen: dict[str, float] = self._load()

    def _load(self) -> dict[str, float]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {str(k): float(v) for k, v in data.items()}
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            log.warning("Не удалось прочитать %s (%s) — начинаю с чистого листа.", self.path, exc)
            return {}

    def filter_new(self, stories: list[Story]) -> list[Story]:
        """Оставляет только те истории, которые ещё не отправлялись."""
        fresh = [s for s in stories if s.id not in self._seen]
        skipped = len(stories) - len(fresh)
        if skipped:
            log.info("Отфильтровано как уже отправленные: %s", skipped)
        return fresh

    def mark_sent(self, items: list[CuratedItem]) -> None:
        """Помечает опубликованные истории как отправленные, чистит протухшие, сохраняет."""
        now = time.time()
        for it in items:
            if it.id:
                self._seen[it.id] = now
        self._prune(now)
        self._save()

    def _prune(self, now: float) -> None:
        before = len(self._seen)
        self._seen = {
            k: ts for k, ts in self._seen.items() if now - ts <= self.ttl_seconds
        }
        removed = before - len(self._seen)
        if removed:
            log.info("Убрано протухших записей (> TTL): %s", removed)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._seen, ensure_ascii=False, indent=0), encoding="utf-8")
        tmp.replace(self.path)  # атомарная замена
        log.info("Сохранено записей в истории отправленного: %s", len(self._seen))
