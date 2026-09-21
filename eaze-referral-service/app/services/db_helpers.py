from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def transaction(session: AsyncSession):
    """`AsyncSession` autobegins a transaction on the first `execute()` — calling the session's
    own `begin()` afterward raises "a transaction is already begun". This wraps a block of
    statements with explicit commit-on-success / rollback-on-exception instead, which works
    whether or not the session has already autobegun."""
    try:
        yield
        await session.commit()
    except Exception:
        await session.rollback()
        raise
