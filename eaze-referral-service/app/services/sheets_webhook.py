"""Best-effort mirror of accepted referrals into a Google Sheet — see
google-apps-script/referral_sheet_webhook.gs for the receiving script and how to deploy it.

Entirely optional and never load-bearing: by the time this runs, the referral itself is already
durably recorded in referral_intents/referral_logs, so a failure here (network, misconfigured
URL, wrong secret, the sheet script erroring) must never surface to the caller or affect the
referral. Called via FastAPI's BackgroundTasks so it can't add latency to the API response
either.
"""

import logging

import httpx

from app.config import Settings

logger = logging.getLogger("eaze_referral.sheets_webhook")


async def notify_google_sheet(referrer_user_id: str, phone_e164: str, settings: Settings) -> None:
    if not settings.google_sheets_webhook_url:
        return

    payload = {"referrerUserId": referrer_user_id, "phoneE164": phone_e164}
    if settings.google_sheets_webhook_secret:
        payload["secret"] = settings.google_sheets_webhook_secret

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(settings.google_sheets_webhook_url, json=payload)
        # Apps Script Web Apps always reply HTTP 200 at the transport level regardless of what
        # the script itself considers an error — the real outcome is in the JSON body's `ok`
        # field, not the status code, so that's what has to be checked here.
        if not response.json().get("ok", False):
            logger.warning(
                "Google Sheets webhook rejected the referral for %s: %s", phone_e164, response.text
            )
    except Exception:
        logger.warning("Google Sheets webhook notify failed for %s", phone_e164, exc_info=True)
