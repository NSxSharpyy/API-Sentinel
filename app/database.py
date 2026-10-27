import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./api_sentinel.db")

engine_options = {}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)


def _async_driver_url(url: str) -> str:
    """Translate supported synchronous database URLs to async drivers."""
    if url.startswith("sqlite+aiosqlite://"):
        return url
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    raise ValueError(
        "Unsupported database URL for async I/O; set ASYNC_DATABASE_URL "
        "to a URL supported by an installed async SQLAlchemy driver."
    )


ASYNC_DATABASE_URL = os.getenv("ASYNC_DATABASE_URL") or _async_driver_url(
    DATABASE_URL
)
# SQLite legacy transaction control can release a SAVEPOINT before the
# outer transaction has begun. Explicit transaction control preserves the
# endpoint + transaction + incident rollback boundary for AsyncSession.
async_engine_options = {}
if ASYNC_DATABASE_URL.startswith("sqlite"):
    async_engine_options["connect_args"] = {"autocommit": False}

async_engine = create_async_engine(
    ASYNC_DATABASE_URL, **async_engine_options
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autoflush=False,
    expire_on_commit=False,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass
