from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Requests/responses use camelCase on the wire (matching the existing eaze-referral-app
    client) while the Python side stays snake_case."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ReferralCodeResponse(CamelModel):
    code: str
    share_url: str


class SubmitIntentsRequest(CamelModel):
    referrer_user_id: str
    phone_numbers_e164: list[str] = Field(min_length=1, max_length=5)


class SkippedPhone(CamelModel):
    phone: str
    reason: str


class SubmitIntentsResponse(CamelModel):
    saved: int
    skipped: list[SkippedPhone]


class SignupMatchRequest(CamelModel):
    phone_e164: str


class SignupMatchResponse(CamelModel):
    user_id: int
    referred: bool
    coins_credited: int = 0


class RechargeWebhookRequest(CamelModel):
    user_id: int
    amount_paise: int
    status: str


class RechargeWebhookResponse(CamelModel):
    credited: bool
    reason: str | None = None
    recharge_id: int
    referrer_user_id: int | None = None


class MessageCopyLogRequest(CamelModel):
    user_id: str


class MessageCopyLogResponse(CamelModel):
    logged: bool


class FunnelCount(CamelModel):
    status: str
    count: int


class FunnelResponse(CamelModel):
    referrals: list[FunnelCount]
    intents: list[FunnelCount]
    total_clicks: int


class ReconcileResponse(CamelModel):
    """Result of one payment-verification pass. `ran=False` with a reason means Redash isn't
    configured — the feature is off, not broken."""

    ran: bool
    reason: str | None = None
    pulled_from_sheet: int = 0
    checked: int = 0
    signups_confirmed: int = 0
    disqualified_already_registered: int = 0
    signup_coins_credited: int = 0
    payments_confirmed: int = 0
    coins_credited: int = 0
    error: str | None = None


class VerificationSummaryResponse(CamelModel):
    """The referral funnel as confirmed facts: referred -> signed up -> paid -> paid out.
    `paid_but_not_credited` is the number that matters operationally — referrals that have
    earned a reward the referrer hasn't received yet."""

    referred: int
    signed_up: int
    paid: int
    referrer_coins_credited: int
    paid_but_not_credited: int
    paid_but_signup_coins_not_credited: int
    disqualified_already_registered: int
    awaiting_phone_check: int
