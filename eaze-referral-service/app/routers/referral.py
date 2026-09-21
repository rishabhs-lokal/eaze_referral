from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.schemas import (
    FunnelResponse,
    RechargeWebhookRequest,
    RechargeWebhookResponse,
    ReferralCodeResponse,
    SignupMatchRequest,
    SignupMatchResponse,
    SkippedPhone,
    SubmitIntentsRequest,
    SubmitIntentsResponse,
)
from app.services import referral_service
from app.services.phone import is_valid_indian_e164

router = APIRouter(prefix="/api/referral", tags=["referral"])


@router.get("/code/{user_id}", response_model=ReferralCodeResponse)
async def get_referral_code(user_id: str, session: AsyncSession = Depends(get_db)) -> ReferralCodeResponse:
    settings = get_settings()
    user = await referral_service.get_or_create_user_by_external_ref(session, user_id)
    code = await referral_service.get_or_create_referral_code(session, user)
    return ReferralCodeResponse(code=code, share_url=f"{settings.public_base_url}/r/{code}")


@router.post("/intents", response_model=SubmitIntentsResponse)
async def submit_intents(
    body: SubmitIntentsRequest, session: AsyncSession = Depends(get_db)
) -> SubmitIntentsResponse:
    referrer = await referral_service.get_or_create_user_by_external_ref(session, body.referrer_user_id)
    saved, skipped = await referral_service.submit_intents(session, referrer, body.phone_numbers_e164)
    return SubmitIntentsResponse(saved=saved, skipped=[SkippedPhone(**s) for s in skipped])


@router.post("/signup-match", response_model=SignupMatchResponse)
async def signup_match(body: SignupMatchRequest, session: AsyncSession = Depends(get_db)) -> SignupMatchResponse:
    if not is_valid_indian_e164(body.phone_e164):
        raise HTTPException(status_code=400, detail="A valid phoneE164 is required")
    try:
        result = await referral_service.signup_match(session, body.phone_e164)
    except referral_service.PhoneAlreadyRegisteredError:
        raise HTTPException(status_code=409, detail="Phone number already registered")
    return SignupMatchResponse(**result)


@router.post("/recharge-webhook", response_model=RechargeWebhookResponse)
async def recharge_webhook(
    body: RechargeWebhookRequest, session: AsyncSession = Depends(get_db)
) -> RechargeWebhookResponse:
    result = await referral_service.recharge_webhook(session, body.user_id, body.amount_paise, body.status)
    return RechargeWebhookResponse(**result)


@router.get("/admin/funnel", response_model=FunnelResponse)
async def admin_funnel(session: AsyncSession = Depends(get_db)) -> FunnelResponse:
    result = await referral_service.admin_funnel(session)
    return FunnelResponse(**result)
