"""Credits coins to a real Eaze wallet.

This is the only thing in the service that moves actual money-equivalent value to a user. Every
other "credit" in this codebase writes to our own tables; this one leaves the building.

Posts a CSV to Eaze's free-coins endpoint, matching the shape of the equivalent Dostt service
(same /payments/free-coins/upload/ path):

    user_id,coins
    <eaze user id>,<amount>

sent as multipart form-data under the field `file`, with the auth key in a configurable header.

Two deliberate behaviours, both of which exist because this moves real coins:

  - Raises on any failure. Unlike the Google Sheet mirror — which is best-effort and swallows
    everything — a failure here MUST propagate, so the caller can roll back its ledger row and
    retry rather than leaving a user marked paid who never received anything.
  - Treats a success-looking HTTP 200 with an error body as a failure. This class of API
    commonly replies 200 and puts the real outcome in the payload, so trusting the status code
    alone would silently drop credits.
"""

import logging

import httpx

from app.config import Settings

logger = logging.getLogger("eaze_referral.eaze_wallet")

_TIMEOUT_SECONDS = 20.0


class WalletCreditError(RuntimeError):
    """The credit did not happen. Callers must roll back and retry — never treat this as paid."""


class WalletNotConfigured(WalletCreditError):
    pass


def is_configured(settings: Settings) -> bool:
    return bool(settings.eaze_free_coins_api_url and settings.eaze_free_coins_auth_key)


def _looks_like_failure(payload: object) -> str | None:
    """Return a reason if the response body indicates failure despite a 2xx status."""
    if not isinstance(payload, dict):
        return None
    if payload.get("success") is False:
        return str(payload.get("message") or payload.get("error") or payload)
    if str(payload.get("status", "")).lower() in {"error", "failed", "failure"}:
        return str(payload.get("message") or payload.get("error") or payload)
    error = payload.get("error")
    if error is True or (isinstance(error, str) and error):
        return str(error)
    return None


async def credit_coins(eaze_user_id: str, coins: int, settings: Settings) -> dict:
    """Credit `coins` to one Eaze user. Raises WalletCreditError if it did not happen."""
    if not is_configured(settings):
        raise WalletNotConfigured(
            "EAZE_FREE_COINS_API_URL / EAZE_FREE_COINS_AUTH_KEY are not set"
        )
    if not eaze_user_id:
        raise WalletCreditError("cannot credit without an Eaze user id")
    if coins <= 0:
        raise WalletCreditError(f"refusing to credit a non-positive amount: {coins}")

    csv_body = f"user_id,coins\n{eaze_user_id},{coins}\n"
    files = {"file": ("coins_batch.csv", csv_body.encode(), "text/csv")}
    data = {"name": settings.eaze_free_coins_batch_name}
    headers = {settings.eaze_free_coins_auth_header: settings.eaze_free_coins_auth_key}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                settings.eaze_free_coins_api_url, files=files, data=data, headers=headers
            )
    except httpx.HTTPError as exc:
        raise WalletCreditError(f"request to the coin API failed: {exc}") from exc

    if response.status_code >= 400:
        raise WalletCreditError(
            f"coin API returned HTTP {response.status_code}: {response.text[:300]}"
        )

    try:
        payload = response.json()
    except ValueError:
        # A non-JSON 2xx is accepted — some upload endpoints reply with plain text. The status
        # code is all we have to go on in that case.
        logger.info("coin API returned non-JSON body for %s: %s", eaze_user_id, response.text[:200])
        return {"raw": response.text}

    reason = _looks_like_failure(payload)
    if reason:
        raise WalletCreditError(f"coin API reported failure: {reason}")

    # The endpoint is ASYNCHRONOUS: it replies 202 "Bulk upload started" with an upload_id and
    # does the actual crediting afterwards. So a success here means ACCEPTED FOR PROCESSING, not
    # "the coins are in the wallet" — if a batch fails inside Eaze later, nothing tells us, and
    # this service will already have recorded the side as credited.
    #
    # The upload_id is logged for exactly that case: it's the only handle for asking Eaze what
    # happened to a batch someone says they never received.
    upload_id = payload.get("upload_id") if isinstance(payload, dict) else None
    logger.info(
        "coin credit accepted for Eaze user %s: %s coins, upload_id=%s (async — acceptance is "
        "not confirmation the wallet was credited)",
        eaze_user_id,
        coins,
        upload_id,
    )
    return payload if isinstance(payload, dict) else {"raw": payload}
