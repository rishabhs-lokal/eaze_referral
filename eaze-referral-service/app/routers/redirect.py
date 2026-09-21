from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import ReferralClick, ReferralCode
from app.services.db_helpers import transaction

router = APIRouter(tags=["redirect"])


@router.get("/r/{code}")
async def click_redirect(code: str, request: Request, session: AsyncSession = Depends(get_db)) -> RedirectResponse:
    """The link embedded in the copyable share message. Logs the click (funnel visibility only —
    never a source of reward attribution, see referral_service.signup_match) then forwards to the
    right store based on user agent."""
    settings = get_settings()

    result = await session.execute(
        select(ReferralCode.id).where(ReferralCode.code == code, ReferralCode.is_active.is_(True))
    )
    code_id = result.scalar_one_or_none()

    if code_id is None:
        return RedirectResponse(settings.fallback_url, status_code=302)

    user_agent = request.headers.get("user-agent", "")
    async with transaction(session):
        session.add(
            ReferralClick(
                referral_code_id=code_id,
                ip_address=request.client.host if request.client else None,
                user_agent=user_agent or None,
            )
        )

    ua = user_agent.lower()
    if "android" in ua:
        target = settings.play_store_url
    elif "iphone" in ua or "ipad" in ua:
        target = settings.app_store_url
    else:
        target = settings.fallback_url

    # Pass the code through as `referrer` too, so a future Play Install Referrer integration
    # (REFERRAL_PROGRAM_PLAN.md §3) can read it straight off the install without extra wiring.
    separator = "&" if "?" in target else "?"
    return RedirectResponse(f"{target}{separator}referrer={code}", status_code=302)
