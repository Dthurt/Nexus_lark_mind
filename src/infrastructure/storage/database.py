"""Async SQLAlchemy engine / session factory."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.common.config import Settings, get_settings
from src.common.errors import StorageError


class Base(DeclarativeBase):
    pass


_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _ensure_sqlite_dir(database_url: str) -> None:
    if "sqlite" not in database_url:
        return
    # sqlite+aiosqlite:///data/nexus.db or ////absolute
    marker = ":///"
    if marker not in database_url:
        return
    path_part = database_url.split(marker, 1)[1]
    if path_part.startswith("/") and not path_part.startswith("///"):
        # relative like data/nexus.db
        db_path = Path(path_part)
    else:
        db_path = Path(path_part)
    if db_path.parent and str(db_path.parent) not in (".", ""):
        db_path.parent.mkdir(parents=True, exist_ok=True)


async def init_database(settings: Optional[Settings] = None) -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    settings = settings or get_settings()
    try:
        _ensure_sqlite_dir(settings.database_url)
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
        )
        _session_factory = async_sessionmaker(
            _engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        # Import models so metadata is populated
        from src.infrastructure.storage import models  # noqa: F401

        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return _session_factory
    except Exception as exc:
        raise StorageError(f"database init failed: {exc}") from exc


async def close_database() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise StorageError("Database not initialized")
    return _session_factory


async def session_scope() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
