"""Runs the verification-and-payout pass on a timer, so people are paid without anyone asking.

Everything else in this service is reactive: a referral arrives, a webhook fires, someone calls
an endpoint. But a referred person paying is an event that happens inside Eaze, and nothing
tells us about it. Without this loop the reconciler never runs and nobody is ever paid, however
correct the rest of the pipeline is.

Runs in-process rather than as a Kubernetes CronJob so it behaves identically under Docker
Compose, a bare `uvicorn`, and Kubernetes — one less thing that works locally and silently
doesn't in production.

The pods problem: with N replicas, N copies of this loop are running. Every write the reconciler
makes is idempotent, so concurrent passes cannot double-pay — but they would each hammer Redash
for the same rows. A Postgres advisory lock means only one pod does the work on any given tick,
and the others skip cheaply. The lock is released as soon as the pass finishes, and is dropped
automatically if a pod dies holding it, because it lives on the connection.
"""

import asyncio
import logging

from sqlalchemy import text

from app.config import Settings
from app.db import get_engine, get_sessionmaker
from app.services import verification

logger = logging.getLogger("eaze_referral.scheduler")

# Arbitrary but fixed: a Postgres advisory lock key is just a 64-bit int that all participants
# agree on. Must stay constant across deploys or two versions could run a pass simultaneously.
_RECONCILE_LOCK_KEY = 8419023571_000_001


async def _run_one_pass(settings: Settings) -> None:
    """Take the lock, run a reconcile, release. Skips entirely if another pod holds it."""
    engine = get_engine()
    async with engine.connect() as conn:
        got_lock = await conn.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": _RECONCILE_LOCK_KEY}
        )
        if not got_lock:
            logger.debug("another instance is reconciling; skipping this tick")
            return
        try:
            async with get_sessionmaker()() as session:
                result = await verification.reconcile(session, settings)
            if result.get("ran"):
                # Only worth a log line when something actually moved — an idle pass every few
                # minutes would otherwise bury real events.
                if result.get("coins_credited") or result.get("signup_coins_credited"):
                    logger.info("reconcile credited coins: %s", result)
                else:
                    logger.debug("reconcile pass: %s", result)
            else:
                logger.debug("reconcile skipped: %s", result.get("reason"))
        finally:
            await conn.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": _RECONCILE_LOCK_KEY}
            )


async def reconcile_loop(settings: Settings) -> None:
    """Forever: wait, then run a pass. Cancelled on shutdown."""
    interval = settings.reconcile_interval_seconds
    logger.info("reconcile loop started, every %ss", interval)
    while True:
        try:
            await asyncio.sleep(interval)
            await _run_one_pass(settings)
        except asyncio.CancelledError:
            logger.info("reconcile loop stopping")
            raise
        except Exception:  # noqa: BLE001
            # A failed pass must never kill the loop — the next tick retries. Redash being down,
            # the coin API refusing, a bad row: all of it is transient from here.
            logger.warning("reconcile pass failed; will retry next tick", exc_info=True)


def start(settings: Settings) -> asyncio.Task | None:
    """Start the loop unless it's switched off. Returns the task so shutdown can cancel it."""
    if settings.reconcile_interval_seconds <= 0:
        logger.info("reconcile loop disabled (RECONCILE_INTERVAL_SECONDS <= 0)")
        return None
    return asyncio.create_task(reconcile_loop(settings), name="reconcile-loop")
