"""All referral business logic. Routers stay thin — they parse/validate the HTTP layer and call
into here; every multi-statement operation owns its own transaction (`async with transaction(session)`)
so a router never has to know about commit/rollback."""

import hashlib
import logging

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import (
    LoginLog,
    MessageCopyLog,
    Recharge,
    Referral,
    ReferralClick,
    ReferralCode,
    ReferralIntent,
    ReferralLog,
    ReferralVerification,
    User,
    WalletTransaction,
)
from app.services.codes import generate_referral_code
from app.services.db_helpers import transaction
from app.services.phone import is_likely_fake, is_valid_indian_e164

logger = logging.getLogger("eaze_referral.service")


class PhoneAlreadyRegisteredError(Exception):
    pass


def _synthetic_phone_for_external_ref(external_ref: str) -> str:
    """Prototype-only shim — see the docstring on User.external_ref. Deterministic so repeated
    calls for the same externalRef resolve to the same synthetic user."""
    digest = hashlib.sha256(external_ref.encode()).hexdigest()
    digits = int(digest[:12], 16) % 1_000_000_000
    return f"+919{digits:09d}"


async def get_or_create_user_by_external_ref(session: AsyncSession, external_ref: str) -> User:
    existing = await session.execute(select(User).where(User.external_ref == external_ref))
    user = existing.scalar_one_or_none()
    if user is not None:
        return user

    phone = _synthetic_phone_for_external_ref(external_ref)
    async with transaction(session):
        stmt = (
            pg_insert(User.__table__)
            .values(phone_e164=phone, external_ref=external_ref)
            .on_conflict_do_update(index_elements=["external_ref"], set_={"external_ref": external_ref})
        )
        await session.execute(stmt)

    result = await session.execute(select(User).where(User.external_ref == external_ref))
    return result.scalar_one()


async def record_first_login(session: AsyncSession, user_id: str) -> None:
    """Idempotent — inserts a row only the first time this user_id is ever seen. Called on every
    GET /api/referral/code/:userId (i.e. every time the webapp loads for that user), but only the
    first call for a given user_id actually writes a row."""
    async with transaction(session):
        stmt = pg_insert(LoginLog.__table__).values(user_id=user_id).on_conflict_do_nothing(index_elements=["user_id"])
        await session.execute(stmt)


async def record_referral_log(session: AsyncSession, user_id: str, phone_numbers: list[str]) -> None:
    """Append-only — logs every validly-formatted phone number a referrer submitted, every time,
    regardless of whether referral_intents ultimately accepted it (e.g. as a duplicate). This is
    a full audit trail, not the attribution source of truth."""
    valid_phones = [p for p in phone_numbers if is_valid_indian_e164(p)]
    if not valid_phones:
        return
    async with transaction(session):
        session.add_all([ReferralLog(user_id=user_id, phone_e164=phone) for phone in valid_phones])


async def record_message_copy(session: AsyncSession, user_id: str) -> None:
    """Every call adds a new row — this is a click counter, not an idempotent/first-seen log.
    COUNT(*) GROUP BY user_id gives the "number of times" a user copied the message."""
    async with transaction(session):
        session.add(MessageCopyLog(user_id=user_id))


async def get_or_create_referral_code(session: AsyncSession, user: User) -> str:
    existing = await session.execute(select(ReferralCode.code).where(ReferralCode.user_id == user.id))
    code = existing.scalar_one_or_none()
    if code:
        return code

    # Retry on the rare code collision (UNIQUE constraint) rather than trusting one draw.
    for _attempt in range(5):
        candidate = generate_referral_code()
        try:
            async with transaction(session):
                stmt = (
                    pg_insert(ReferralCode.__table__)
                    .values(user_id=user.id, code=candidate)
                    .on_conflict_do_update(index_elements=["user_id"], set_={"is_active": True})
                )
                await session.execute(stmt)
            break
        except IntegrityError:
            continue
    else:
        raise RuntimeError("Could not allocate a referral code")

    result = await session.execute(select(ReferralCode.code).where(ReferralCode.user_id == user.id))
    return result.scalar_one()


async def submit_intents(
    session: AsyncSession, referrer: User, phone_numbers: list[str]
) -> tuple[int, list[dict]]:
    """A number is only ever accepted into referral_intents when it doesn't already exist
    there (enforced below AND by the table's own UNIQUE constraint as a second line of
    defense — see referral_intents_phone_e164_key) and isn't already a registered Eaze user
    — the referral bonus never applies to someone already on Eaze (see the Eligibility
    section of the Terms), so accepting that number here would create a referral that can
    never be rewarded."""
    saved = 0
    skipped: list[dict] = []

    async with transaction(session):
        valid_phones = [p for p in phone_numbers if is_valid_indian_e164(p)]
        registered_result = await session.execute(
            select(User.phone_e164).where(User.phone_e164.in_(valid_phones))
        )
        already_registered_phones = {row[0] for row in registered_result.all()}

        for phone in phone_numbers:
            if not is_valid_indian_e164(phone):
                skipped.append({"phone": phone, "reason": "invalid_format"})
                continue
            if phone == referrer.phone_e164:
                skipped.append({"phone": phone, "reason": "self_referral"})
                continue
            if phone in already_registered_phones:
                skipped.append({"phone": phone, "reason": "already_registered"})
                continue
            if is_likely_fake(phone):
                skipped.append({"phone": phone, "reason": "likely_fake"})
                continue

            stmt = (
                pg_insert(ReferralIntent.__table__)
                .values(referrer_user_id=referrer.id, phone_e164=phone)
                .on_conflict_do_nothing(index_elements=["phone_e164"])
                .returning(ReferralIntent.__table__.c.id)
            )
            result = await session.execute(stmt)
            intent_row = result.first()
            if intent_row is None:
                skipped.append({"phone": phone, "reason": "already_referred"})
                continue

            saved += 1
            # Open the tracking row at the same moment the referral becomes real, in the same
            # transaction. Starting it here (rather than at signup) is the whole point: a
            # number that is referred and then never signs up, or signs up and never pays, is
            # only visible because a row was opened the moment it was referred.
            await session.execute(
                pg_insert(ReferralVerification.__table__)
                .values(
                    phone_e164=phone,
                    referrer_external_id=referrer.external_ref,
                    referrer_user_id=referrer.id,
                    referral_intent_id=intent_row.id,
                )
                .on_conflict_do_nothing(index_elements=["phone_e164"])
            )

    return saved, skipped


async def signup_match(session: AsyncSession, phone_e164: str, settings: Settings) -> dict:
    """Stands in for the hook the real Eaze signup flow would call right after OTP verification
    succeeds for a brand-new phone number.

    Attribution is phone-only: a referral exists if and only if this exact number was
    pre-entered by a referrer via submit_intents. There is no code/deep-link fallback — if the
    number wasn't named up front, this is just a normal signup with no bonus for anyone.
    """
    async with transaction(session):
        already = await session.execute(select(User.id).where(User.phone_e164 == phone_e164))
        if already.scalar_one_or_none() is not None:
            raise PhoneAlreadyRegisteredError()

        new_user = User(phone_e164=phone_e164)
        session.add(new_user)
        await session.flush()  # assigns new_user.id without committing

        intent_result = await session.execute(
            select(ReferralIntent).where(
                ReferralIntent.phone_e164 == phone_e164, ReferralIntent.status == "PENDING"
            )
        )
        intent = intent_result.scalar_one_or_none()
        referrer_user_id = intent.referrer_user_id if intent else None

        if not referrer_user_id or referrer_user_id == new_user.id:
            return {"user_id": new_user.id, "referred": False, "coins_credited": 0}

        referral_stmt = (
            pg_insert(Referral.__table__)
            .values(
                referrer_user_id=referrer_user_id,
                referred_user_id=new_user.id,
                referred_phone_e164=phone_e164,
                referral_intent_id=intent.id,
                signup_rewarded_at=func.now(),
            )
            .on_conflict_do_nothing(index_elements=["referred_user_id"])
            .returning(Referral.__table__.c.id)
        )
        referral_result = await session.execute(referral_stmt)
        referral_row = referral_result.first()
        referral_id = referral_row.id if referral_row else None

        if referral_id:
            await session.execute(
                update(ReferralIntent.__table__)
                .where(ReferralIntent.id == intent.id)
                .values(status="MATCHED", matched_user_id=new_user.id, matched_at=func.now())
            )
            # Signing up records the relationship — it does NOT pay anyone. Both rewards are
            # gated on the referred person actually paying (see the Coin Crediting section of
            # the Terms): they are credited together by _credit_both_on_payment, from either
            # the recharge webhook or the Redash reconciler. Leaving both coin statuses PENDING
            # here is the gate.
            await session.execute(
                update(ReferralVerification.__table__)
                .where(ReferralVerification.phone_e164 == phone_e164)
                .values(
                    referral_id=referral_id,
                    signup_status="SIGNED_UP",
                    signed_up_at=func.now(),
                    updated_at=func.now(),
                )
            )

        return {
            "user_id": new_user.id,
            "referred": referral_id is not None,
            "coins_credited": 0,
        }


async def recharge_webhook(
    session: AsyncSession, user_id: int, amount_paise: int, status: str, settings: Settings
) -> dict:
    """Stands in for the payment gateway webhook. Credits the referrer only on the referred
    user's first-ever successful recharge, idempotently."""
    async with transaction(session):
        recharge_result = await session.execute(
            pg_insert(Recharge.__table__)
            .values(user_id=user_id, amount_paise=amount_paise, status=status)
            .returning(Recharge.__table__.c.id)
        )
        recharge_id = recharge_result.scalar_one()

        if status != "SUCCESS":
            return {"credited": False, "reason": "recharge_not_successful", "recharge_id": recharge_id}

        count_result = await session.execute(
            select(Recharge.id).where(Recharge.user_id == user_id, Recharge.status == "SUCCESS")
        )
        if len(count_result.all()) != 1:
            return {"credited": False, "reason": "not_first_recharge", "recharge_id": recharge_id}

        updated = await session.execute(
            update(Referral.__table__)
            .where(Referral.referred_user_id == user_id, Referral.status == "SIGNED_UP")
            .values(
                status="REWARDED",
                recharge_rewarded_at=func.now(),
                triggering_recharge_id=recharge_id,
                updated_at=func.now(),
            )
            .returning(
                Referral.__table__.c.id,
                Referral.__table__.c.referrer_user_id,
                Referral.__table__.c.referred_phone_e164,
            )
        )
        referral_row = updated.first()
        if referral_row is None:
            return {"credited": False, "reason": "no_pending_referral", "recharge_id": recharge_id}

        referral_id, referrer_user_id = referral_row.id, referral_row.referrer_user_id
        referred_phone = referral_row.referred_phone_e164

        paid = await credit_both_on_payment(
            session,
            referral_id=referral_id,
            referrer_user_id=referrer_user_id,
            referred_user_id=user_id,
            referred_phone_e164=referred_phone,
            settings=settings,
            first_payment_amount_paise=amount_paise,
        )
        if not paid["eligible"]:
            return {
                "credited": False,
                "reason": paid["reason"],
                "recharge_id": recharge_id,
            }

        return {
            "credited": True,
            "referrer_user_id": referrer_user_id,
            "recharge_id": recharge_id,
            "referred_phone_e164": referred_phone,
        }


async def credit_both_on_payment(
    session: AsyncSession,
    *,
    referral_id: int,
    referrer_user_id: int,
    referred_user_id: int,
    referred_phone_e164: str,
    settings: Settings,
    first_payment_amount_paise: int | None = None,
    payment_count: int = 1,
) -> dict:
    """Pay BOTH sides of a referral, because the referred person actually paid.

    A confirmed payment is the single event that releases coins — for the referrer AND for the
    person referred. Signing up alone pays nobody (see the Coin Crediting section of the Terms).
    Keeping both credits in one function is what makes that guarantee checkable: there is no
    other code path that moves referral coins.

    Called from two places, and safe from both at once:
      - recharge_webhook, on the payment event itself
      - the Redash reconciler, when it finds a real payment the webhook never reported

    Both wallet inserts go through wallet_transactions' UNIQUE(user_id, type, reference_id), so
    whichever path arrives second moves nothing. Must be called inside a transaction.
    """
    # A number that was already an Eaze user when it was referred can never earn coins, however
    # much it later pays — the bonus does not apply to existing users. This is the last gate
    # before money moves, deliberately re-checked here rather than trusted from the caller.
    check = await session.execute(
        select(ReferralVerification.phone_check_status).where(
            ReferralVerification.phone_e164 == referred_phone_e164
        )
    )
    if check.scalar_one_or_none() == "ALREADY_REGISTERED":
        return {"eligible": False, "reason": "phone_already_registered", "credited": []}

    credited: list[str] = []
    for who, wallet_user_id, amount, tx_type in (
        ("referred", referred_user_id, settings.signup_bonus_coins, "REFERRAL_SIGNUP_BONUS"),
        ("referrer", referrer_user_id, settings.recharge_bonus_coins, "REFERRAL_RECHARGE_BONUS"),
    ):
        ledger = await session.execute(
            pg_insert(WalletTransaction.__table__)
            .values(
                user_id=wallet_user_id,
                amount=amount,
                type=tx_type,
                reference_type="referral",
                reference_id=referral_id,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "type", "reference_id"])
            .returning(WalletTransaction.__table__.c.id)
        )
        if ledger.first() is not None:
            await session.execute(
                update(User.__table__)
                .where(User.id == wallet_user_id)
                .values(wallet_balance=User.wallet_balance + amount)
            )
            credited.append(who)

    await session.execute(
        update(Referral.__table__)
        .where(Referral.id == referral_id)
        .values(
            status="REWARDED",
            signup_rewarded_at=func.coalesce(Referral.signup_rewarded_at, func.now()),
            recharge_rewarded_at=func.coalesce(Referral.recharge_rewarded_at, func.now()),
            updated_at=func.now(),
        )
    )
    values: dict = {
        "payment_status": "PAID",
        "successful_payment_count": payment_count,
        "signup_coins_status": "CREDITED",
        "signup_coins_amount": settings.signup_bonus_coins,
        "signup_coins_credited_at": func.now(),
        "referrer_coins_status": "CREDITED",
        "referrer_coins_amount": settings.recharge_bonus_coins,
        "referrer_coins_credited_at": func.now(),
        "first_payment_at": func.coalesce(ReferralVerification.first_payment_at, func.now()),
        "updated_at": func.now(),
    }
    if first_payment_amount_paise is not None:
        values["first_payment_amount_paise"] = first_payment_amount_paise
    await session.execute(
        update(ReferralVerification.__table__)
        .where(ReferralVerification.phone_e164 == referred_phone_e164)
        .values(**values)
    )

    return {"eligible": True, "reason": None, "credited": credited}


async def admin_funnel(session: AsyncSession) -> dict:
    referrals_by_status = await session.execute(select(Referral.status, func.count()).group_by(Referral.status))
    intents_by_status = await session.execute(
        select(ReferralIntent.status, func.count()).group_by(ReferralIntent.status)
    )
    total_clicks = await session.execute(select(func.count()).select_from(ReferralClick))

    return {
        "referrals": [{"status": s, "count": c} for s, c in referrals_by_status.all()],
        "intents": [{"status": s, "count": c} for s, c in intents_by_status.all()],
        "total_clicks": total_clicks.scalar_one(),
    }
