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
import datetime as dt
import logging

from sqlalchemy import text

from app.config import Settings
from app.db import get_engine, get_sessionmaker
from app.services import payout_window, verification

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


def _sleep_seconds(settings: Settings) -> float:
    """How long to wait before the next pass.

    With a payout window configured the loop runs ONLY inside it: closed, it sleeps straight
    through to the next opening; open, it ticks at `reconcile_interval_seconds` so several
    passes fit in the window. There is no all-day cadence any more.

    That means the reconcile pass — which is also what confirms payments against Redash — runs
    once a night rather than every 15 minutes. Deliberate, and the cost is stated where it will
    be noticed: the funnel, the verification summary and the Google Sheet only advance in the
    window, so during the day they describe last night. Nothing is lost, only delayed; the
    queue is durable and a payment confirmed at noon is still confirmed at midnight.

    Sleeping exactly to the opening rather than ticking past it is what makes a pass certain at
    window open whatever time the process started. A fixed interval would step over a 30-minute
    window after an awkward restart — up at 00:29, next tick 00:44, window gone, every due
    payout waiting another 24 hours with no symptom but silence.

    With the window disabled (PAYOUT_WINDOW_MINUTES=0) this falls back to the plain interval,
    which is how the service behaved before the window existed.
    """
    interval = float(settings.reconcile_interval_seconds)
    if not payout_window.is_enabled(settings):
        return interval
    until_open = payout_window.seconds_until_open(dt.datetime.now(dt.timezone.utc), settings)
    # 0 means the window is open right now: tick at the interval so the queue gets several
    # passes before it closes, rather than busy-looping or waiting out the whole window.
    if until_open == 0:
        return interval
    return until_open


async def reconcile_loop(settings: Settings) -> None:
    """Forever: wait, then run a pass. Cancelled on shutdown."""
    interval = settings.reconcile_interval_seconds
    if payout_window.is_enabled(settings):
        logger.info(
            "reconcile loop started: passes ONLY inside the %s, every %ss while it is open",
            payout_window.describe(settings),
            interval,
        )
    else:
        logger.info("reconcile loop started, every %ss, payout window disabled", interval)
    while True:
        try:
            await asyncio.sleep(_sleep_seconds(settings))
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
