"""Generic async Postgres client.

Works against any Postgres-wire-compatible database — vanilla Postgres, RDS, Cloud SQL, Supabase,
Neon, CockroachDB in Postgres mode — because it's built on nothing but a standard connection URL
and the asyncpg driver. No vendor-specific connector, no assumed IAM auth, no hardcoded host.

Safe for multiple Kubernetes pods: each pod gets its own bounded connection pool (sized via
DB_POOL_SIZE / DB_POOL_MAX_OVERFLOW so N replicas' total connections stay predictable against the
database's max_connections), and get_engine()/get_sessionmaker() are process-local singletons —
there is no shared mutable state between pods, and none needed.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from app.config import Settings, get_settings

logger = logging.getLogger("eaze_referral.db")


def to_asyncpg_url(database_url: str) -> str:
    """Accepts a plain postgresql:// URL (the portable, provider-agnostic form used in every
    Postgres tool's docs) and adapts it to the asyncpg driver SQLAlchemy needs, without requiring
    callers to know the driver detail."""
    parts = urlsplit(database_url)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def _connect_args(settings: Settings) -> dict:
    if settings.database_ssl_mode.lower() not in ("disable", "false", "0", ""):
        return {"ssl": True}
    return {}


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        to_asyncpg_url(settings.database_url),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=True,  # cheap liveness check per checkout; avoids handing out dead connections
        connect_args=_connect_args(settings),
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=get_engine(), expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — one session per request, always closed."""
    async with get_sessionmaker()() as session:
        yield session


async def wait_for_database(settings: Settings | None = None) -> None:
    """Retries the initial connectivity check with backoff. Covers the case where a pod starts
    before the database is reachable — a fresh cluster still bringing up its Postgres, a managed
    instance mid-failover, a Compose `depends_on` race. Raises after exhausting the budget so the
    pod fails its startup instead of serving traffic against a database it never reached."""
    settings = settings or get_settings()
    engine = get_engine()
    last_error: Exception | None = None
    for attempt in range(1, settings.db_startup_retry_attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database reachable after %d attempt(s)", attempt)
            return
        except Exception as exc:  # noqa: BLE001 - deliberately broad, this is a connectivity probe
            last_error = exc
            logger.warning(
                "Database not reachable yet (attempt %d/%d): %s",
                attempt,
                settings.db_startup_retry_attempts,
                exc,
            )
            await asyncio.sleep(settings.db_startup_retry_delay_seconds)
    raise ConnectionError(
        f"Could not reach the database after {settings.db_startup_retry_attempts} attempts"
    ) from last_error


async def is_database_ready() -> bool:
    """Cheap per-request check for the /readyz probe — not the startup retry loop."""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False
