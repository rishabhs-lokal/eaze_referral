from fastapi import APIRouter, Response

from app.db import is_database_ready

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness — deliberately does NOT touch the database. A transient DB blip shouldn't cause
    Kubernetes to kill and restart otherwise-healthy pods; that's what /readyz is for."""
    return {"ok": True}


@router.get("/readyz")
async def readyz(response: Response) -> dict:
    """Readiness — this pod is pulled out of the Service's endpoints if this fails, without being
    restarted. Checks the database is actually reachable."""
    ready = await is_database_ready()
    if not ready:
        response.status_code = 503
    return {"ready": ready}
