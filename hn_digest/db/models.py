"""ORM-модели: посты дайджеста и личное состояние пользователя."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Post(Base):
    """Один отобранный `CuratedItem` в рамках выпуска за конкретную дату."""

    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("digest_date", "hn_id", name="uq_posts_date_hn"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hn_id: Mapped[str] = mapped_column(Text)
    digest_date: Mapped[date] = mapped_column(Date, index=True)
    title_ru: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    verdict: Mapped[str] = mapped_column(Text, default="")
    why: Mapped[str] = mapped_column(Text, default="")
    tag: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    hn_url: Mapped[str] = mapped_column(Text, default="")
    points: Mapped[int] = mapped_column(Integer, default=0)
    num_comments: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer)  # порядок внутри дня (0-based)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserPost(Base):
    """Личное состояние пользователя по посту: просмотрено / сохранено.

    Строка появляется лениво — при первом просмотре или сохранении. Отсутствие
    строки эквивалентно «не просмотрено и не сохранено».
    """

    __tablename__ = "user_post"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user id
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
