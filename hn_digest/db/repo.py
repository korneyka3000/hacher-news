"""Async-запросы к БД. Функции не коммитят — транзакцией управляет вызывающий."""

from __future__ import annotations

from datetime import date

from sqlalchemy import and_, distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CuratedItem
from .models import Post, UserPost

# Поля поста, которые перезаписываем при повторной курации того же дня.
_UPSERT_FIELDS = (
    "title_ru",
    "summary",
    "verdict",
    "why",
    "tag",
    "url",
    "hn_url",
    "points",
    "num_comments",
    "position",
)


async def insert_digest(session: AsyncSession, items: list[CuratedItem], digest_date: date) -> None:
    """Upsert выпуска: по (digest_date, hn_id), с сохранением порядка в `position`."""
    if not items:
        return
    rows = [
        {
            "hn_id": it.id,
            "digest_date": digest_date,
            "title_ru": it.title_ru,
            "summary": it.summary,
            "verdict": it.verdict,
            "why": it.why,
            "tag": it.tag,
            "url": it.url,
            "hn_url": it.hn_url,
            "points": it.points,
            "num_comments": it.num_comments,
            "position": i,
        }
        for i, it in enumerate(items)
    ]
    stmt = pg_insert(Post).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["digest_date", "hn_id"],
        set_={f: getattr(stmt.excluded, f) for f in _UPSERT_FIELDS},
    )
    await session.execute(stmt)


async def list_dates(
    session: AsyncSession, user_id: int, limit: int, offset: int
) -> list[tuple[date, int, int]]:
    """Даты выпусков (свежие сверху) с (всего, непросмотрено-у-пользователя)."""
    stmt = (
        select(
            Post.digest_date,
            func.count(Post.id).label("total"),
            func.count().filter(UserPost.viewed_at.is_(None)).label("unviewed"),
        )
        .select_from(Post)
        .outerjoin(
            UserPost,
            and_(UserPost.post_id == Post.id, UserPost.user_id == user_id),
        )
        .group_by(Post.digest_date)
        .order_by(Post.digest_date.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = await session.execute(stmt)
    return [(r.digest_date, r.total, r.unviewed) for r in rows]


async def count_dates(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(distinct(Post.digest_date)))) or 0)


async def get_posts_for_date(session: AsyncSession, digest_date: date) -> list[Post]:
    stmt = select(Post).where(Post.digest_date == digest_date).order_by(Post.position)
    return list(await session.scalars(stmt))


async def latest_date(session: AsyncSession) -> date | None:
    return await session.scalar(select(func.max(Post.digest_date)))


async def _viewed_ids(session: AsyncSession, user_id: int, post_ids: list[int]) -> set[int]:
    if not post_ids:
        return set()
    stmt = select(UserPost.post_id).where(
        UserPost.user_id == user_id,
        UserPost.post_id.in_(post_ids),
        UserPost.viewed_at.is_not(None),
    )
    return set(await session.scalars(stmt))


async def first_unviewed_index(session: AsyncSession, user_id: int, digest_date: date) -> int:
    """Индекс первого непросмотренного поста дня; 0, если всё просмотрено/пусто."""
    posts = await get_posts_for_date(session, digest_date)
    if not posts:
        return 0
    viewed = await _viewed_ids(session, user_id, [p.id for p in posts])
    for i, p in enumerate(posts):
        if p.id not in viewed:
            return i
    return 0


async def get_post(session: AsyncSession, post_id: int) -> Post | None:
    return await session.get(Post, post_id)


async def get_state(session: AsyncSession, user_id: int, post_id: int) -> tuple[bool, bool]:
    """Возвращает (просмотрено, сохранено) для пары пользователь–пост."""
    up = await session.get(UserPost, (user_id, post_id))
    if up is None:
        return (False, False)
    return (up.viewed_at is not None, up.saved_at is not None)


async def mark_viewed(session: AsyncSession, user_id: int, post_id: int) -> bool:
    """Помечает просмотренным. True — если это первый просмотр (для бейджа 🆕)."""
    up = await session.get(UserPost, (user_id, post_id))
    if up is None:
        session.add(UserPost(user_id=user_id, post_id=post_id, viewed_at=func.now()))
        return True
    if up.viewed_at is None:
        up.viewed_at = func.now()
        return True
    return False


async def toggle_saved(session: AsyncSession, user_id: int, post_id: int) -> bool:
    """Переключает сохранение. Возвращает новое состояние (True — сохранено)."""
    up = await session.get(UserPost, (user_id, post_id))
    if up is None:
        session.add(UserPost(user_id=user_id, post_id=post_id, saved_at=func.now()))
        return True
    if up.saved_at is None:
        up.saved_at = func.now()
        return True
    up.saved_at = None
    return False


async def list_saved(session: AsyncSession, user_id: int, limit: int, offset: int) -> list[Post]:
    """Сохранённые пользователем посты, свежесохранённые сверху."""
    stmt = (
        select(Post)
        .join(UserPost, and_(UserPost.post_id == Post.id, UserPost.user_id == user_id))
        .where(UserPost.saved_at.is_not(None))
        .order_by(UserPost.saved_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(stmt))


async def count_saved(session: AsyncSession, user_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(UserPost)
        .where(UserPost.user_id == user_id, UserPost.saved_at.is_not(None))
    )
    return int(await session.scalar(stmt) or 0)
