"""Async SQLAlchemy engine / session factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator, Optional

from sqlalchemy import event, text
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


def _sqlite_connect_args(database_url: str) -> dict[str, Any]:
    """Reduce 'database is locked' under concurrent agent/session writes."""
    if "sqlite" not in (database_url or ""):
        return {}
    # aiosqlite / sqlite3: wait up to 30s on write contention instead of failing immediately
    return {"timeout": 30}


def _configure_sqlite_connection(dbapi_connection: Any, _connection_record: Any) -> None:
    # Applied on every new DB-API connection (including aiosqlite).
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
    finally:
        cursor.close()


async def init_database(settings: Optional[Settings] = None) -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    settings = settings or get_settings()
    try:
        _ensure_sqlite_dir(settings.database_url)
        connect_args = _sqlite_connect_args(settings.database_url)
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
            connect_args=connect_args,
        )
        if "sqlite" in settings.database_url:
            # sync engine underneath async engine — attach PRAGMA on connect
            event.listen(_engine.sync_engine, "connect", _configure_sqlite_connection)

        _session_factory = async_sessionmaker(
            _engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        # Import models so metadata is populated
        from src.infrastructure.storage import models  # noqa: F401
        from src.core_kernel.plugin_runtime.knowledge_store import (  # noqa: F401
            KnowledgeChunk,
            KnowledgeDoc,
            KnowledgeSyncLog,
        )

        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            if "sqlite" in settings.database_url:
                # Ensure WAL is set even if no fresh connect hook ran yet
                await conn.execute(text("PRAGMA journal_mode=WAL"))
                await conn.execute(text("PRAGMA synchronous=NORMAL"))
                await conn.execute(text("PRAGMA busy_timeout=30000"))
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


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise StorageError("Database not initialized")
    return _engine


async def session_scope() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
