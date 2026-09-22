from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.schemas import (
    FunnelResponse,
    MessageCopyLogRequest,
    MessageCopyLogResponse,
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
from app.services.identity import decode_user_id
from app.services.phone import is_valid_indian_e164

router = APIRouter(prefix="/api/referral", tags=["referral"])


def _decode_or_400(raw: str) -> str:
    """Every externally-supplied user_id arrives base64-encoded (see
    eaze-referral-app/src/state/useReferrerId.ts) and is decoded here, once, at the API
    boundary — everything downstream (users.external_ref, login_logs, referral_logs,
    message_copy_logs) stores and queries the real user id, never the base64 form of it."""
    try:
        return decode_user_id(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id")


@router.get("/code/{user_id}", response_model=ReferralCodeResponse)
async def get_referral_code(user_id: str, session: AsyncSession = Depends(get_db)) -> ReferralCodeResponse:
    settings = get_settings()
    decoded_id = _decode_or_400(user_id)
    await referral_service.record_first_login(session, decoded_id)
    user = await referral_service.get_or_create_user_by_external_ref(session, decoded_id)
    code = await referral_service.get_or_create_referral_code(session, user)
    return ReferralCodeResponse(code=code, share_url=f"{settings.public_base_url}/r/{code}")


@router.post("/intents", response_model=SubmitIntentsResponse)
async def submit_intents(
    body: SubmitIntentsRequest, session: AsyncSession = Depends(get_db)
) -> SubmitIntentsResponse:
    decoded_id = _decode_or_400(body.referrer_user_id)
    referrer = await referral_service.get_or_create_user_by_external_ref(session, decoded_id)
    await referral_service.record_referral_log(session, decoded_id, body.phone_numbers_e164)
    saved, skipped = await referral_service.submit_intents(session, referrer, body.phone_numbers_e164)
    return SubmitIntentsResponse(saved=saved, skipped=[SkippedPhone(**s) for s in skipped])


@router.post("/copy-log", response_model=MessageCopyLogResponse)
async def log_message_copy(
    body: MessageCopyLogRequest, session: AsyncSession = Depends(get_db)
) -> MessageCopyLogResponse:
    decoded_id = _decode_or_400(body.user_id)
    await referral_service.record_message_copy(session, decoded_id)
    return MessageCopyLogResponse(logged=True)


@router.post("/signup-match", response_model=SignupMatchResponse)
async def signup_match(body: SignupMatchRequest, session: AsyncSession = Depends(get_db)) -> SignupMatchResponse:
    if not is_valid_indian_e164(body.phone_e164):
        raise HTTPException(status_code=400, detail="A valid phoneE164 is required")
    settings = get_settings()
    try:
        result = await referral_service.signup_match(session, body.phone_e164, settings)
    except referral_service.PhoneAlreadyRegisteredError:
        raise HTTPException(status_code=409, detail="Phone number already registered")
    return SignupMatchResponse(**result)


@router.post("/recharge-webhook", response_model=RechargeWebhookResponse)
async def recharge_webhook(
    body: RechargeWebhookRequest, session: AsyncSession = Depends(get_db)
) -> RechargeWebhookResponse:
    settings = get_settings()
    result = await referral_service.recharge_webhook(
        session, body.user_id, body.amount_paise, body.status, settings
    )
    return RechargeWebhookResponse(**result)


@router.get("/admin/funnel", response_model=FunnelResponse)
async def admin_funnel(session: AsyncSession = Depends(get_db)) -> FunnelResponse:
    result = await referral_service.admin_funnel(session)
    return FunnelResponse(**result)
