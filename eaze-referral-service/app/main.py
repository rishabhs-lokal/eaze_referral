import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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

# The referral page itself, built into ./web by the Dockerfile's first stage and served from the
# same origin as the API it calls. Mounted LAST and deliberately: Starlette matches routes in
# registration order, so /healthz, /api/referral/* and /r/{code} are all claimed above before
# anything reaches this catch-all.
#
# Same origin is the point. A separately hosted page would need its own DNS record, its own TLS
# certificate, and CORS — three things that can be wrong in ways that look like the app being
# broken. Here the page can only ever talk to the service that served it.
#
# Absent in a dev checkout, where the frontend runs under `expo start` on its own port. The
# directory check keeps `uvicorn app.main:app` working there rather than failing on a path that
# only exists inside the image.
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if _WEB_DIR.is_dir():
    # html=True serves index.html for "/" and for unknown paths, which is what a single-page app
    # needs — the route lives in the client, not here.
    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
    logger.info("serving the referral page from %s", _WEB_DIR)
else:
    logger.info("no built referral page at %s — API only", _WEB_DIR)
