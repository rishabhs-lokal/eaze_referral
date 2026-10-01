import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import get_engine, wait_for_database
from app.routers import health, redirect, referral
from app.services import scheduler

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger("eaze_referral")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Fail startup loudly if the database is never reachable, rather than serving traffic that
    # can only ever 500. Kubernetes will restart the pod and retry per its own backoff.
    await wait_for_database(settings)
    logger.info("eaze-referral-service starting up")

    # Start the payout loop. Without it the service would decide correctly who is owed coins and
    # then never act on it, because nothing external triggers a payout — see scheduler.py.
    reconcile_task = scheduler.start(settings)

    yield

    logger.info("eaze-referral-service shutting down")
    if reconcile_task is not None:
        reconcile_task.cancel()
        with suppress(asyncio.CancelledError):
            await reconcile_task
    await get_engine().dispose()


app = FastAPI(title="eaze-referral-service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(referral.router)
app.include_router(redirect.router)
