"""Доменные модели."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Story:
    """Кандидат — история с Hacker News до курации."""

    id: str
    title: str
    url: str
    hn_url: str
    points: int
    num_comments: int
    author: str
    is_show_hn: bool
    text: str


@dataclass(slots=True)
class CuratedItem:
    """Отобранная и разобранная Claude история для публикации."""

    id: str
    title_ru: str
    summary: str
    verdict: str
    why: str
    tag: str
    # Обогащается из исходной Story:
    url: str = ""
    hn_url: str = ""
    points: int = 0
    num_comments: int = 0

    @classmethod
    def from_claude(cls, raw: dict, story: Story | None) -> CuratedItem:
        """Собирает элемент из ответа Claude + данных исходной истории."""
        return cls(
            id=str(raw.get("id", "")),
            title_ru=str(raw.get("title_ru") or "").strip(),
            summary=str(raw.get("summary") or "").strip(),
            verdict=str(raw.get("verdict") or "").strip(),
            why=str(raw.get("why") or "").strip(),
            tag=str(raw.get("tag") or "").strip(),
            url=story.url if story else "",
            hn_url=story.hn_url if story else "",
            points=story.points if story else 0,
            num_comments=story.num_comments if story else 0,
        )
