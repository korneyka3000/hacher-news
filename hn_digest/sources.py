"""Сбор кандидатов из Hacker News через Algolia API.

Ссылочные истории (внешний url, пустой story_text) до передачи в LLM обогащаются
мета-контекстом страницы (title/description) — чтобы Claude видел суть статьи, а не
только заголовок. Обогащение best-effort и не роняет прогон при ошибках сети.
"""

from __future__ import annotations

import html
import re
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from .config import Settings
from .logging_setup import get_logger
from .models import Story

log = get_logger(__name__)

USER_AGENT = "hn-digest/0.2 (+https://news.ycombinator.com)"
ALGOLIA = "https://hn.algolia.com/api/v1"
ENRICH_TIMEOUT = 6.0  # короткий таймаут на страницу — обогащение best-effort
_TAG_RE = re.compile(r"<[^>]+>")
_META_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r"""(\w[\w:-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_DESC_KEYS = ("description", "og:description", "twitter:description")


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
                text=_clean_text(hit.get("story_text") or "", 600),
            )

    candidates = sorted(seen.values(), key=lambda s: s.points, reverse=True)
    log.info("Собрано кандидатов: %s", len(candidates))
    return candidates


def _clean_text(raw: str, limit: int) -> str:
    """HTML → чистый текст: снять теги, раскодировать сущности, схлопнуть пробелы.

    Обрезка по границе предложения (или слова), а не посреди слова.
    """
    text = " ".join(_TAG_RE.sub(" ", html.unescape(raw)).split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in (". ", "! ", "? "):
        idx = cut.rfind(sep)
        if idx >= limit * 0.6:  # режем по концу предложения, если он не слишком рано
            return cut[: idx + 1].strip()
    idx = cut.rfind(" ")
    return (cut[:idx] if idx > 0 else cut).strip() + "…"


def enrich_links(stories: list[Story], top_n: int) -> None:
    """Обогащает top-N ссылочных историй мета-контекстом страницы (in-place).

    Вызывается ПОСЛЕ антидублей — чтобы не ходить в сеть за историями, которые
    всё равно будут отброшены как уже отправленные.
    """
    if top_n <= 0:
        return
    targets = [s for s in stories if not s.text and s.url != s.hn_url][:top_n]
    if not targets:
        return
    log.info("Обогащаю мета-контекстом ссылок: %s", len(targets))
    with ThreadPoolExecutor(max_workers=8) as pool:
        contexts = list(pool.map(lambda s: _fetch_meta(s.url), targets))
    for story, ctx in zip(targets, contexts, strict=True):
        if ctx:
            story.text = ctx
    log.info("Обогащено ссылок: %s/%s", sum(1 for s in targets if s.text), len(targets))


def _fetch_meta(url: str) -> str:
    """GET страницы → короткая аннотация (meta description). Best-effort, «» при ошибке."""
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=ENRICH_TIMEOUT,
            follow_redirects=True,
        )
        if resp.status_code != 200 or "html" not in resp.headers.get("content-type", "").lower():
            return ""
        return _extract_meta_context(resp.text[:200_000])
    except Exception as exc:  # noqa: BLE001
        log.debug("Обогащение не удалось %s: %s", url, exc)
        return ""


def _extract_meta_context(page_html: str) -> str:
    """Достаёт лучшее (самое длинное) описание из meta/og/twitter тегов."""
    best = ""
    for tag in _META_RE.findall(page_html):
        attrs: dict[str, str] = {}
        for m in _ATTR_RE.finditer(tag):
            attrs[m.group(1).lower()] = m.group(2) if m.group(2) is not None else m.group(3)
        kind = (attrs.get("name") or attrs.get("property") or "").lower()
        content = attrs.get("content", "")
        if kind in _DESC_KEYS and content and len(content) > len(best):
            best = content
    return _clean_text(best, 400)
