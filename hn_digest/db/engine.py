"""Async-движок SQLAlchemy для Neon Postgres.

DATABASE_URL хранится в libpq-форме (`postgresql://…?sslmode=require`), а здесь
приводится к asyncpg. Так как используем pooled-эндпоинт Neon (PgBouncer,
transaction mode), отключаем кэш prepared-statements на обоих уровнях и берём
NullPool — после scale-to-zero старые TCP-коннекты всё равно мертвы, держать их
в пуле смысла нет.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# libpq-only параметры, которые asyncpg не понимает — выкидываем из URL.
_LIBPQ_ONLY = {"sslmode", "channel_binding", "options", "target_session_attrs"}


def to_asyncpg_url(raw: str) -> str:
    """Приводит любой Postgres DSN к форме `postgresql+asyncpg://` без libpq-хвостов."""
    parts = urlsplit(raw)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _LIBPQ_ONLY
    ]
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def make_engine(database_url: str) -> AsyncEngine:
    """Создаёт async-движок под Neon pooled endpoint."""
    return create_async_engine(
        to_asyncpg_url(database_url),
        poolclass=NullPool,
        connect_args={
            "ssl": "require",  # Neon требует TLS; cert валиден, verify не обязателен
            "statement_cache_size": 0,  # asyncpg: без client-side кэша под PgBouncer
            "prepared_statement_cache_size": 0,  # SQLAlchemy asyncpg-адаптер: тоже без кэша
        },
    )


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий; expire_on_commit=False — объекты живут после commit."""
    return async_sessionmaker(engine, expire_on_commit=False)
