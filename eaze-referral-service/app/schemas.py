from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Requests/responses use camelCase on the wire (matching the existing eaze-referral-app
    client) while the Python side stays snake_case."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ReferralCodeResponse(CamelModel):
    code: str
    share_url: str
    # The referrer's allowance, resolved server-side. The page reads the limit from here rather
    # than inlining its own copy, so the two can never disagree and changing it is a ConfigMap
    # edit rather than a rebuild.
    referrals_used: int
    referrals_limit: int


# A bound on request SIZE, deliberately not the referral cap. The cap is per referrer and
# depends on how many slots that person has already spent, which only the service layer knows —
# tying this constant to max_referrals_per_user would mean raising the cap silently started
# rejecting requests at the HTTP layer instead.
MAX_PHONES_PER_REQUEST = 10


class SubmitIntentsRequest(CamelModel):
    referrer_user_id: str
    phone_numbers_e164: list[str] = Field(min_length=1, max_length=MAX_PHONES_PER_REQUEST)


class SkippedPhone(CamelModel):
    phone: str
    reason: str


class SubmitIntentsResponse(CamelModel):
    saved: int
    skipped: list[SkippedPhone]
    # Where the referrer stands after this submission. Returned so the page can update its
    # remaining-invites state from the same transaction that just changed it, rather than
    # re-fetching and racing its own write.
    referrals_used: int
    referrals_limit: int


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
    # Referrals retired this pass for never producing a signup. Reported so a sudden spike
    # is visible — a misconfigured REFERRAL_EXPIRY_DAYS would otherwise silently retire
    # live referrals and look exactly like a quiet day.
    expired_no_signup: int = 0
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
    expired_no_signup: int = 0
    # When the longest-waiting unsettled referral was last looked at. Every other field
    # here says what happened; this one says whether the queue is keeping up. Each pass
    # covers at most redash_batch_size rows, so once the outstanding count exceeds that,
    # this timestamp starts sliding and nothing else would show it.
    oldest_pending_checked_at: str | None = None
