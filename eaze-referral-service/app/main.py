import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import get_engine, wait_for_database
from app.routers import health, redirect, referral

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger("eaze_referral")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Fail startup loudly if the database is never reachable, rather than serving traffic that
    # can only ever 500. Kubernetes will restart the pod and retry per its own backoff.
    await wait_for_database(settings)
    logger.info("eaze-referral-service starting up")
    yield
    logger.info("eaze-referral-service shutting down")
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
