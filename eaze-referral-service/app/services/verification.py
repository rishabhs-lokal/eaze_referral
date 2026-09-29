"""Independent confirmation that a referred person really signed up and really paid, before
the referrer's coins are credited.

Why this exists on top of the recharge webhook: the webhook is a claim made by a caller. It is
the right trigger for the happy path, but it is not evidence. This reconciler is the evidence —
it asks Redash (which runs against Eaze's real user and payment tables) two questions per
referred number:

    1. Does this phone number correspond to a real registered Eaze user?   (phone -> user_id)
    2. Has that user actually completed a successful payment?              (user_id -> payments)

Only a yes to both releases the referrer's reward. Everything it learns is written to
referral_verifications, so the table is a standing answer to "which referred numbers signed up,
which paid, and who has actually been paid out".

Design rules, all of which matter because this moves money:

  - Crediting goes through the same idempotency guard as the webhook path
    (wallet_transactions' UNIQUE(user_id, type, reference_id)), so a referrer can never be paid
    twice for one referral no matter how often this runs or how the two paths interleave.
  - A Redash failure is never read as "they didn't pay". It's recorded on the row as an error
    and retried on the next run. Withholding an earned reward because a dashboard was down
    would be the worst possible failure mode here.
  - The reconciler only ever advances a row. It never revokes coins already credited; a
    reversal is a deliberate, separate decision, not something a background sweep should do.
"""

import datetime as dt
import logging

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Referral, ReferralVerification, User, WalletTransaction
from app.services import redash
from app.services.db_helpers import transaction

logger = logging.getLogger("eaze_referral.verification")


def _parse_timestamp(value) -> dt.datetime | None:
    """Redash hands back whatever the warehouse driver serialised — usually an ISO string,
    sometimes already a datetime, sometimes null. Anything unparseable is treated as "no
    timestamp" rather than failing the whole batch: the payment flag is what gates the reward,
    the exact timestamp is reporting detail."""
    if value is None or isinstance(value, dt.datetime):
        return value
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def _pending_rows(session: AsyncSession, limit: int) -> list[ReferralVerification]:
    """Rows still worth asking Redash about: anything whose payment isn't confirmed yet, or
    that is confirmed paid but whose referrer hasn't been credited (the case a webhook outage
    or a mid-flight crash leaves behind — exactly what a reconciler is for)."""
    result = await session.execute(
        select(ReferralVerification)
        .where(
            or_(
                ReferralVerification.payment_status == "PENDING",
                ReferralVerification.referrer_coins_status == "PENDING",
            )
        )
        .order_by(ReferralVerification.last_checked_at.asc().nulls_first())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _resolve_eaze_user_ids(
    settings: Settings, phones: list[str]
) -> dict[str, dict]:
    """Query 1 — phone number to real Eaze user. Returns {phone_e164: row}."""
    rows = await redash.run_query(
        settings,
        settings.redash_verify_phone_query_id,
        {"mobile_numbers": ",".join(phones)},
    )
    resolved: dict[str, dict] = {}
    for row in rows:
        raw_phone = str(row.get("mobile_no") or "")
        digits = "".join(c for c in raw_phone if c.isdigit())[-10:]
        if digits:
            resolved[f"+91{digits}"] = row
    return resolved


async def _fetch_payments(settings: Settings, user_ids: list[str]) -> dict[str, dict]:
    """Query 2 — real payment facts per Eaze user id. Returns {user_id: row}."""
    rows = await redash.run_query(
        settings,
        settings.redash_payments_query_id,
        {"user_ids": ",".join(user_ids)},
    )
    return {str(row.get("user_id")): row for row in rows if row.get("user_id") is not None}


async def _credit_referrer(
    session: AsyncSession, row: ReferralVerification, settings: Settings
) -> bool:
    """Credit the referrer for a confirmed-paid referral. Returns True if coins were actually
    moved by this call, False if the ledger shows they already had been.

    The wallet_transactions insert is the authority, not the referral_verifications row: if
    ON CONFLICT swallows the insert, the referrer was already paid for this referral (by the
    webhook path, or an earlier run of this reconciler) and the balance must not move again.
    We still stamp the tracking row in that case, so it reflects the ledger's truth.
    """
    referral_id = row.referral_id
    if referral_id is None:
        result = await session.execute(
            select(Referral.id).where(Referral.referred_phone_e164 == row.phone_e164)
        )
        referral_id = result.scalar_one_or_none()
        if referral_id is None:
            # Paid, but we have no referral record to pay against — a signup that never came
            # through our own signup_match. Left PENDING deliberately so it shows up as
            # outstanding rather than being silently closed.
            return False

    ledger = await session.execute(
        pg_insert(WalletTransaction.__table__)
        .values(
            user_id=row.referrer_user_id,
            amount=settings.recharge_bonus_coins,
            type="REFERRAL_RECHARGE_BONUS",
            reference_type="referral",
            reference_id=referral_id,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "type", "reference_id"])
        .returning(WalletTransaction.__table__.c.id)
    )
    newly_credited = ledger.first() is not None

    if newly_credited:
        await session.execute(
            update(User.__table__)
            .where(User.id == row.referrer_user_id)
            .values(wallet_balance=User.wallet_balance + settings.recharge_bonus_coins)
        )
        await session.execute(
            update(Referral.__table__)
            .where(Referral.id == referral_id, Referral.status == "SIGNED_UP")
            .values(
                status="REWARDED",
                recharge_rewarded_at=func.now(),
                updated_at=func.now(),
            )
        )

    await session.execute(
        update(ReferralVerification.__table__)
        .where(ReferralVerification.id == row.id)
        .values(
            referral_id=referral_id,
            referrer_coins_status="CREDITED",
            referrer_coins_amount=settings.recharge_bonus_coins,
            referrer_coins_credited_at=func.now(),
            updated_at=func.now(),
        )
    )
    return newly_credited


async def reconcile(session: AsyncSession, settings: Settings, limit: int | None = None) -> dict:
    """Run one reconciliation pass. Safe to call repeatedly and concurrently with the webhook
    path — every write it makes is idempotent."""
    if not redash.is_configured(settings):
        return {"ran": False, "reason": "redash_not_configured"}
    if not settings.redash_verify_phone_query_id or not settings.redash_payments_query_id:
        return {"ran": False, "reason": "redash_query_ids_not_configured"}

    batch_limit = limit or settings.redash_batch_size
    rows = await _pending_rows(session, batch_limit)
    if not rows:
        return {"ran": True, "checked": 0, "signups_confirmed": 0, "payments_confirmed": 0, "coins_credited": 0}

    stats = {"ran": True, "checked": len(rows), "signups_confirmed": 0, "payments_confirmed": 0, "coins_credited": 0}

    # Step 1 — resolve every number that doesn't yet have an Eaze user id.
    unresolved = [r.phone_e164 for r in rows if not r.eaze_user_id]
    resolved: dict[str, dict] = {}
    if unresolved:
        try:
            resolved = await _resolve_eaze_user_ids(settings, unresolved)
        except redash.RedashError as exc:
            logger.warning("Redash phone lookup failed: %s", exc)
            await _record_error(session, [r.id for r in rows], str(exc))
            return {**stats, "error": str(exc)}

    async with transaction(session):
        for row in rows:
            match = resolved.get(row.phone_e164)
            if match and match.get("user_id") is not None:
                row.eaze_user_id = str(match["user_id"])
                row.signup_status = "SIGNED_UP"
                row.signed_up_at = row.signed_up_at or _parse_timestamp(match.get("registered_at"))
                row.source = "REDASH"
                stats["signups_confirmed"] += 1
            elif row.phone_e164 in unresolved and row.signup_status == "PENDING":
                # Asked about it, warehouse has no such user — they genuinely haven't
                # registered (yet). Not an error, and re-checked on the next pass.
                # Guarded on PENDING so this can only ever fill in an unknown, never
                # contradict a signup our own pipeline already saw and rewarded.
                row.signup_status = "NOT_FOUND"

    # Step 2 — ask about payments for everyone we now have an Eaze id for.
    payable = [r for r in rows if r.eaze_user_id and r.referrer_coins_status == "PENDING"]
    if not payable:
        await _stamp_checked(session, [r.id for r in rows])
        return stats

    try:
        payments = await _fetch_payments(settings, [r.eaze_user_id for r in payable])
    except redash.RedashError as exc:
        logger.warning("Redash payment lookup failed: %s", exc)
        await _record_error(session, [r.id for r in payable], str(exc))
        return {**stats, "error": str(exc)}

    async with transaction(session):
        for row in payable:
            payment = payments.get(row.eaze_user_id)
            paid_count = int(payment.get("successful_payment_count") or 0) if payment else 0

            if paid_count <= 0:
                # Confirmed no payment yet. The referrer is simply not owed anything — this is
                # the check working, not a failure. Stays PENDING and is re-checked.
                row.payment_status = "NO_PAYMENT"
                row.last_error = None
                continue

            row.payment_status = "PAID"
            row.successful_payment_count = paid_count
            row.first_payment_at = row.first_payment_at or _parse_timestamp(
                payment.get("first_payment_at")
            )
            if payment.get("first_payment_amount_paise") is not None:
                row.first_payment_amount_paise = int(payment["first_payment_amount_paise"])
            row.source = "REDASH"
            row.last_error = None
            stats["payments_confirmed"] += 1

            if await _credit_referrer(session, row, settings):
                stats["coins_credited"] += 1

    await _stamp_checked(session, [r.id for r in rows])
    return stats


async def _stamp_checked(session: AsyncSession, row_ids: list[int]) -> None:
    if not row_ids:
        return
    async with transaction(session):
        await session.execute(
            update(ReferralVerification.__table__)
            .where(ReferralVerification.id.in_(row_ids))
            .values(
                last_checked_at=func.now(),
                check_count=ReferralVerification.check_count + 1,
                updated_at=func.now(),
            )
        )


async def _record_error(session: AsyncSession, row_ids: list[int], message: str) -> None:
    """Park the failure on the affected rows so a stuck referral is diagnosable from the table
    alone. Deliberately does not change any status column — a Redash outage says nothing about
    whether someone paid."""
    if not row_ids:
        return
    async with transaction(session):
        await session.execute(
            update(ReferralVerification.__table__)
            .where(ReferralVerification.id.in_(row_ids))
            .values(
                last_checked_at=func.now(),
                check_count=ReferralVerification.check_count + 1,
                last_error=message[:1000],
                updated_at=func.now(),
            )
        )


async def verification_summary(session: AsyncSession) -> dict:
    """Counts behind the funnel: referred -> signed up -> paid -> referrer actually paid out."""
    total = await session.execute(select(func.count()).select_from(ReferralVerification))
    signed_up = await session.execute(
        select(func.count()).select_from(ReferralVerification).where(
            ReferralVerification.signup_status == "SIGNED_UP"
        )
    )
    paid = await session.execute(
        select(func.count()).select_from(ReferralVerification).where(
            ReferralVerification.payment_status == "PAID"
        )
    )
    credited = await session.execute(
        select(func.count()).select_from(ReferralVerification).where(
            ReferralVerification.referrer_coins_status == "CREDITED"
        )
    )
    awaiting = await session.execute(
        select(func.count()).select_from(ReferralVerification).where(
            ReferralVerification.payment_status == "PAID",
            ReferralVerification.referrer_coins_status == "PENDING",
        )
    )
    return {
        "referred": total.scalar_one(),
        "signed_up": signed_up.scalar_one(),
        "paid": paid.scalar_one(),
        "referrer_coins_credited": credited.scalar_one(),
        "paid_but_not_credited": awaiting.scalar_one(),
    }
