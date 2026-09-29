"""Async Redash API client.

Redash is how this service reaches Eaze's *real* user and payment data: the referral database
this app owns only knows what it was told, and what it was told about a payment is exactly the
thing we must not take on trust before paying out coins. Redash queries run against the real
warehouse, so a payment confirmed here is a payment that actually happened.

Redash's results API is asynchronous: asking for results either returns a cached result inline
or hands back a job to poll. `run_query` hides that — give it a query id and parameters, get
rows back.

    rows = await run_query(settings, query_id=17538, params={"mobile_numbers": "+919876543210"})

Requires REDASH_BASE_URL and REDASH_API_KEY. Query ids are configured per-query in Settings —
see the "Payment verification via Redash" section of the README for the two queries this
service expects and the exact SQL shape each must return.
"""

import asyncio
import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger("eaze_referral.redash")

_POLL_INTERVAL_SECONDS = 2.0
_POLL_TIMEOUT_SECONDS = 120.0
_REQUEST_TIMEOUT_SECONDS = 30.0

# Redash job status codes (from Redash's own API): 1=PENDING 2=STARTED 3=SUCCESS 4=FAILURE
# 5=CANCELLED.
_JOB_SUCCESS = 3
_JOB_FAILURE = 4
_JOB_CANCELLED = 5


class RedashError(RuntimeError):
    """Any failure talking to Redash. Callers treat this as "could not verify right now" —
    never as "verified false", because those are very different things when money is involved:
    the first means retry later, the second would mean withholding a legitimately earned
    reward."""


class RedashNotConfigured(RedashError):
    pass


def is_configured(settings: Settings) -> bool:
    return bool(settings.redash_base_url and settings.redash_api_key)


async def _poll_job(client: httpx.AsyncClient, job_id: str) -> int:
    """Poll a Redash job to completion and return its query_result_id."""
    deadline = asyncio.get_running_loop().time() + _POLL_TIMEOUT_SECONDS

    while asyncio.get_running_loop().time() < deadline:
        response = await client.get(f"/api/jobs/{job_id}")
        response.raise_for_status()
        job = response.json().get("job", {})
        status = job.get("status")

        if status == _JOB_SUCCESS:
            return job["query_result_id"]
        if status == _JOB_FAILURE:
            raise RedashError(f"Redash job failed: {job.get('error')}")
        if status == _JOB_CANCELLED:
            raise RedashError("Redash job was cancelled")

        await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    raise RedashError(f"Redash job {job_id} timed out after {_POLL_TIMEOUT_SECONDS}s")


async def run_query(
    settings: Settings,
    query_id: int,
    params: dict[str, Any] | None = None,
    max_age_seconds: int = 0,
) -> list[dict[str, Any]]:
    """Execute a Redash query and return its result rows.

    `max_age_seconds=0` (the default here, deliberately) means never serve a cached result —
    always re-run against the warehouse. Payment verification is exactly the case where a
    stale answer is worse than a slow one: a cached "no payment yet" would keep a referrer
    waiting for a reward they've already earned.
    """
    if not is_configured(settings):
        raise RedashNotConfigured("REDASH_BASE_URL and REDASH_API_KEY must both be set")

    body: dict[str, Any] = {"max_age": max_age_seconds}
    if params:
        body["parameters"] = params

    async with httpx.AsyncClient(
        base_url=settings.redash_base_url.rstrip("/"),
        headers={"Authorization": f"Key {settings.redash_api_key}"},
        timeout=_REQUEST_TIMEOUT_SECONDS,
    ) as client:
        try:
            response = await client.post(f"/api/queries/{query_id}/results", json=body)
            response.raise_for_status()
            data = response.json()

            # Cached result came back inline — no job to poll.
            if "query_result" in data:
                return data["query_result"]["data"]["rows"]

            if "job" in data:
                result_id = await _poll_job(client, data["job"]["id"])
                result_response = await client.get(f"/api/query_results/{result_id}.json")
                result_response.raise_for_status()
                return result_response.json()["query_result"]["data"]["rows"]
        except httpx.HTTPError as exc:
            raise RedashError(f"Redash request failed: {exc}") from exc
        except (KeyError, ValueError) as exc:
            raise RedashError(f"Unexpected Redash response shape: {exc}") from exc

    raise RedashError("Unexpected Redash response: neither query_result nor job present")
