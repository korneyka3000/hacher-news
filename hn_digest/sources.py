"""Сбор кандидатов из Hacker News через Algolia API."""

from __future__ import annotations

import re
import time

import httpx

from .config import Settings
from .logging_setup import get_logger
from .models import Story

log = get_logger(__name__)

USER_AGENT = "hn-digest/0.2 (+https://news.ycombinator.com)"
ALGOLIA = "https://hn.algolia.com/api/v1"


def _get_json(url: str, retries: int = 3) -> dict:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            log.warning("GET неуспешен (%s/%s) %s: %s", attempt, retries, url, exc)
            time.sleep(2 * attempt)
    raise RuntimeError(f"Не удалось получить {url}: {last_err}")


def fetch_candidates(settings: Settings) -> list[Story]:
    """Тянет фронтпейдж + Show HN, дедуплицирует и фильтрует по порогам."""
    cutoff = time.time() - settings.hn_lookback_hours * 3600
    seen: dict[str, Story] = {}

    sources = [
        f"{ALGOLIA}/search?tags=front_page&hitsPerPage={settings.hn_frontpage_count}",
        f"{ALGOLIA}/search_by_date?tags=show_hn&hitsPerPage={settings.hn_showhn_count}",
    ]

    for url in sources:
        try:
            data = _get_json(url)
        except RuntimeError as exc:
            log.error("%s", exc)
            continue
        for hit in data.get("hits", []):
            oid = hit.get("objectID")
            if not oid or oid in seen:
                continue
            points = hit.get("points") or 0
            created = hit.get("created_at_i") or 0
            is_show = "show_hn" in (hit.get("_tags") or [])
            # Show HN проходит без порога рейтинга (свежие запуски).
            if not is_show and points < settings.hn_min_points:
                continue
            if created and created < cutoff:
                continue
            title = (hit.get("title") or "").strip()
            if not title:
                continue
            seen[oid] = Story(
                id=oid,
                title=title,
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                hn_url=f"https://news.ycombinator.com/item?id={oid}",
                points=points,
                num_comments=hit.get("num_comments") or 0,
                author=hit.get("author") or "",
                is_show_hn=is_show,
                text=re.sub(r"<[^>]+>", " ", hit.get("story_text") or "")[:600],
            )

    candidates = sorted(seen.values(), key=lambda s: s.points, reverse=True)
    log.info("Собрано кандидатов: %s", len(candidates))
    return candidates
