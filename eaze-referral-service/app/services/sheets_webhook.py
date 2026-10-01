"""Best-effort mirror of the referral pipeline into a Google Sheet — see
google-apps-script/referral_sheet_webhook.gs for the receiving script and how to deploy it.

Two things happen here: a row is added when a referral is accepted, and that row is advanced as
the number moves through verification and payout, so the sheet shows current state rather than
just "this was submitted once".

Entirely optional and never load-bearing. By the time any of this runs the underlying fact is
already durably recorded in Postgres, so a failure here (network, misconfigured URL, wrong
secret, the sheet script erroring) must never surface to the caller or affect a referral or a
payout. Every function below swallows its own errors by design.
"""

import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger("eaze_referral.sheets_webhook")

_TIMEOUT_SECONDS = 10.0


async def _post(settings: Settings, payload: dict[str, Any], context: str) -> dict | None:
    """Send one action to the Apps Script Web App. Returns the parsed body, or None on any
    failure — callers treat None as "the sheet didn't get the message", never as an error
    worth propagating."""
    if not settings.google_sheets_webhook_url:
        return None
    if settings.google_sheets_webhook_secret:
        payload = {**payload, "secret": settings.google_sheets_webhook_secret}

    # Apps Script intermittently serves a Drive HTML error page instead of running the script —
    # seen right after deploying a new version, and occasionally afterwards. It isn't a real
    # failure, so one retry turns a spurious miss into a success rather than a lost sheet update.
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT_SECONDS, follow_redirects=True
            ) as client:
                response = await client.post(settings.google_sheets_webhook_url, json=payload)

            # Apps Script Web Apps always reply HTTP 200 at the transport level regardless of
            # what the script itself considers an error — the real outcome is in the JSON
            # body's `ok` field, not the status code, so that's what has to be checked here.
            try:
                body = response.json()
            except ValueError:
                if attempt == 1:
                    continue
                logger.warning(
                    "Google Sheet returned a non-JSON response for %s (HTTP %s)",
                    context,
                    response.status_code,
                )
                return None

            if not body.get("ok", False):
                logger.warning("Google Sheet rejected %s: %s", context, response.text[:300])
                return None
            return body
        except Exception:
            if attempt == 1:
                continue
            logger.warning("Google Sheet %s failed", context, exc_info=True)
            return None
    return None


async def notify_google_sheet(referrer_user_id: str, phone_e164: str, settings: Settings) -> None:
    """Add a row when a referral is accepted."""
    await _post(
        settings,
        {"action": "append", "referrerUserId": referrer_user_id, "phoneE164": phone_e164},
        f"append for {phone_e164}",
    )


async def update_sheet_status(
    phone_e164: str,
    settings: Settings,
    *,
    verification: str | None = None,
    payment: str | None = None,
    friend_coins: str | None = None,
    referrer_coins: str | None = None,
) -> None:
    """Advance an existing row. Only the fields actually passed are written, so a verification
    result can't overwrite payout columns and vice versa."""
    if not settings.google_sheets_webhook_url:
        return

    payload: dict[str, Any] = {"action": "update", "phoneE164": phone_e164}
    if verification is not None:
        payload["verification"] = verification
    if payment is not None:
        payload["payment"] = payment
    if friend_coins is not None:
        payload["friendCoins"] = friend_coins
    if referrer_coins is not None:
        payload["referrerCoins"] = referrer_coins

    await _post(settings, payload, f"status update for {phone_e164}")


async def list_sheet_rows(settings: Settings, only_verified: bool = False) -> list[dict]:
    """Pull the phone numbers back out of the sheet.

    Note this is a convenience/ops view, not an input to the reward pipeline: referral coins are
    always decided from referral_verifications in Postgres, never from the sheet. A spreadsheet
    anyone can hand-edit must not be able to move money.
    """
    body = await _post(settings, {"action": "list", "onlyVerified": only_verified}, "list")
    return body.get("rows", []) if body else []
