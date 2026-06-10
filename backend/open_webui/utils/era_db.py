"""
Database connection manager for the ERA (Dr. Boz) account database.
Provides async session access to the external era SQLite database.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from open_webui.env import DATA_DIR

log = logging.getLogger(__name__)

# Path to the ERA account database
ERA_DB_PATH = os.environ.get('ERA_DB_PATH', os.path.join(DATA_DIR, 'era.db'))

_async_engine = None
_async_session_factory = None


def _get_engine():
    """Lazy-initialize the async engine for the ERA database."""
    global _async_engine, _async_session_factory
    if _async_engine is None:
        if not os.path.exists(ERA_DB_PATH):
            log.warning(f'ERA database not found at {ERA_DB_PATH}. Account features will be unavailable.')
            return None
        db_url = f'sqlite+aiosqlite:///{ERA_DB_PATH}'
        _async_engine = create_async_engine(
            db_url,
            connect_args={'check_same_thread': False},
            pool_size=50,
            pool_pre_ping=True,
        )
        _async_session_factory = async_sessionmaker(
            bind=_async_engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        log.info(f'ERA database connected at {ERA_DB_PATH}')
    return _async_engine


def get_era_session_factory():
    """Get the async session factory for the ERA database."""
    engine = _get_engine()
    if engine is None:
        return None
    return _async_session_factory


@asynccontextmanager
async def get_era_session():
    """Async context manager for ERA database sessions."""
    factory = get_era_session_factory()
    if factory is None:
        raise RuntimeError('ERA database not available')
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def is_era_db_available() -> bool:
    """Check if the ERA database is available."""
    return os.path.exists(ERA_DB_PATH) and _get_engine() is not None
