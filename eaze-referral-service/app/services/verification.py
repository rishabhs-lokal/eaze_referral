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
from app.db import get_sessionmaker
from app.models import Referral, ReferralIntent, ReferralVerification, User
from app.services import redash, referral_service
from app.services.db_helpers import transaction
from app.services.sheets_webhook import list_sheet_rows, update_sheet_status

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


def _normalise_sheet_phone(value: object) -> str | None:
    """Turn whatever the Sheet gives back into the E.164 form the database stores.

    Google Sheets silently coerces a cell that looks numeric into a number, so "+919876543210"
    comes back as the integer 919876543210 — the leading plus is simply gone. Comparing that
    against phone_e164 matches nothing, which would narrow every reconcile pass to zero rows
    and quietly stop all payouts. Rebuild the canonical form from the digits instead of
    trusting the cell's type.
    """
    if value is None:
        return None
    digits = "".join(c for c in str(value) if c.isdigit())
    if len(digits) < 10:
        return None
    return f"+91{digits[-10:]}"


async def _pending_rows(
    session: AsyncSession, limit: int, phones: list[str] | None = None
) -> list[ReferralVerification]:
    """Rows still worth asking Redash about: a number whose pre-existing-user check never
    completed, a payment not yet confirmed, or coins still owed to either side (what a webhook
    outage or a mid-flight crash leaves behind — exactly what a reconciler is for).

    Rows already disqualified as ALREADY_REGISTERED are excluded outright: that verdict is
    final, so there is nothing left to ask about them.

    `phones` narrows the pass to the numbers pulled from the Google Sheet. It can only ever
    narrow: a number in the sheet that has no row here is ignored rather than acted on, so a
    hand-edited spreadsheet can't invent a referral or move coins. The sheet chooses WHICH
    referrals to look at; the database remains the authority on whether they're real.
    """
    query = select(ReferralVerification).where(
        ReferralVerification.phone_check_status != "ALREADY_REGISTERED",
        or_(
            ReferralVerification.phone_check_status == "UNCHECKED",
            ReferralVerification.payment_status == "PENDING",
            ReferralVerification.referrer_coins_status == "PENDING",
            ReferralVerification.signup_coins_status == "PENDING",
        ),
    )
    if phones:
        query = query.where(ReferralVerification.phone_e164.in_(phones))

    result = await session.execute(
        query.order_by(ReferralVerification.last_checked_at.asc().nulls_first()).limit(limit)
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


async def _ensure_local_user(session: AsyncSession, phone_e164: str) -> int:
    """Get (or create) the local `users` row for a referred phone number.

    Creating one here is bookkeeping, not account creation — `users` is this service's minimal
    stand-in for the real Eaze user table (see its docstring), and by the time we get here
    Redash has already confirmed the person is a genuinely registered Eaze user. Without this,
    a signup that Eaze processed but never told us about could never be rewarded, because there
    would be no local id to credit.
    """
    result = await session.execute(select(User.id).where(User.phone_e164 == phone_e164))
    user_id = result.scalar_one_or_none()
    if user_id is not None:
        return user_id

    await session.execute(
        pg_insert(User.__table__)
        .values(phone_e164=phone_e164)
        .on_conflict_do_nothing(index_elements=["phone_e164"])
    )
    result = await session.execute(select(User.id).where(User.phone_e164 == phone_e164))
    return result.scalar_one()


async def _ensure_referral(
    session: AsyncSession, row: ReferralVerification, referred_user_id: int
) -> int | None:
    """The referral record a signup reward has to hang off. Returns None when one can't
    legitimately exist — no originating intent, or referrer and referred turning out to be the
    same person (which the referrals table's own no_self_referral constraint would reject
    anyway)."""
    if row.referral_id is not None:
        return row.referral_id

    existing = await session.execute(
        select(Referral.id).where(Referral.referred_phone_e164 == row.phone_e164)
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        return found

    if row.referral_intent_id is None or referred_user_id == row.referrer_user_id:
        return None

    created = await session.execute(
        pg_insert(Referral.__table__)
        .values(
            referrer_user_id=row.referrer_user_id,
            referred_user_id=referred_user_id,
            referred_phone_e164=row.phone_e164,
            referral_intent_id=row.referral_intent_id,
        )
        .on_conflict_do_nothing(index_elements=["referred_user_id"])
        .returning(Referral.__table__.c.id)
    )
    created_row = created.first()
    if created_row is None:
        # Raced with another writer (or the webhook path) — take whatever landed.
        fallback = await session.execute(
            select(Referral.id).where(Referral.referred_user_id == referred_user_id)
        )
        return fallback.scalar_one_or_none()

    await session.execute(
        update(ReferralIntent.__table__)
        .where(ReferralIntent.id == row.referral_intent_id, ReferralIntent.status == "PENDING")
        .values(status="MATCHED", matched_user_id=referred_user_id, matched_at=func.now())
    )
    return created_row.id


async def verify_submitted_phone(phone_e164: str, settings: Settings) -> None:
    """Check a freshly-submitted number against the real Eaze user base.

    The rule, straight from the Eligibility section of the Terms: the referral bonus does not
    apply to a phone number already registered on Eaze. So the question asked here is "does
    this number already belong to an Eaze account?" — the Redash phone query returning nothing
    is what verifies it. A hit means this was never a valid referral and it is disqualified
    before it can accumulate any reward state.

    Runs as a FastAPI BackgroundTask after the response has gone out, because Redash's job
    polling can take seconds to minutes and must never sit in front of a user pressing Save.
    Anything it can't check stays UNCHECKED and is retried by the reconciler, so a Redash
    outage delays verification rather than losing it.

    Opens its own session: by the time this runs the request's session is closed.
    """
    if not redash.is_configured(settings) or not settings.redash_verify_phone_query_id:
        return

    try:
        matches = await _resolve_eaze_user_ids(settings, [phone_e164])
    except redash.RedashError as exc:
        logger.warning("phone verification failed for %s: %s", phone_e164, exc)
        return

    match = matches.get(phone_e164)
    async with get_sessionmaker()() as session:
        async with transaction(session):
            if match and match.get("user_id") is not None:
                await session.execute(
                    update(ReferralVerification.__table__)
                    .where(ReferralVerification.phone_e164 == phone_e164)
                    .values(
                        phone_check_status="ALREADY_REGISTERED",
                        pre_existing_eaze_user_id=str(match["user_id"]),
                        phone_checked_at=func.now(),
                        updated_at=func.now(),
                    )
                )
                # Kill the intent too, so nothing downstream can match a signup to it and
                # build a referral on a number that was never eligible.
                await session.execute(
                    update(ReferralIntent.__table__)
                    .where(
                        ReferralIntent.phone_e164 == phone_e164,
                        ReferralIntent.status == "PENDING",
                    )
                    .values(status="EXPIRED")
                )
                logger.info(
                    "referral disqualified — %s is already Eaze user %s",
                    phone_e164,
                    match["user_id"],
                )
            else:
                await session.execute(
                    update(ReferralVerification.__table__)
                    .where(ReferralVerification.phone_e164 == phone_e164)
                    .values(
                        phone_check_status="VERIFIED",
                        phone_checked_at=func.now(),
                        updated_at=func.now(),
                    )
                )

    # Mirror the verdict into the sheet, after the database has it. Best-effort by design.
    await update_sheet_status(
        phone_e164,
        settings,
        verification="Already registered" if match else "Verified",
    )


async def reconcile(session: AsyncSession, settings: Settings, limit: int | None = None) -> dict:
    """Run one reconciliation pass. Safe to call repeatedly and concurrently with the webhook
    path — every write it makes is idempotent."""
    if not redash.is_configured(settings):
        return {"ran": False, "reason": "redash_not_configured"}
    if not settings.redash_verify_phone_query_id or not settings.redash_payments_query_id:
        return {"ran": False, "reason": "redash_query_ids_not_configured"}

    batch_limit = limit or settings.redash_batch_size

    # Pull the phone numbers from the Google Sheet — that's the working list of who's been
    # referred. Falls back to the database queue when the sheet is unreachable or empty, so a
    # Sheets outage delays nothing: people owed coins still get paid.
    sheet_phones: list[str] = []
    try:
        sheet_rows = await list_sheet_rows(settings)
        sheet_phones = [
            p for r in sheet_rows if (p := _normalise_sheet_phone(r.get("phoneE164")))
        ]
    except Exception:  # noqa: BLE001 - the sheet is never allowed to break a payout run
        logger.warning("could not pull phone numbers from the sheet", exc_info=True)

    rows = await _pending_rows(session, batch_limit, phones=sheet_phones or None)

    # A sheet that returned numbers but matched nothing in the database is a signal, not a
    # result: it means the two have drifted (a renamed column, a cleared sheet, a formatting
    # change) and narrowing to it would silently process zero referrals and pay nobody, while
    # every log line still said the pass ran fine. Fall back to the database queue instead.
    if sheet_phones and not rows:
        logger.warning(
            "sheet returned %d numbers but none matched a pending referral — falling back to "
            "the database queue",
            len(sheet_phones),
        )
        rows = await _pending_rows(session, batch_limit)
    elif sheet_phones:
        logger.info("pulled %d phone numbers from the sheet", len(sheet_phones))
    empty = {
        "pulled_from_sheet": len(sheet_phones),
        "signups_confirmed": 0,
        "disqualified_already_registered": 0,
        "signup_coins_credited": 0,
        "payments_confirmed": 0,
        "coins_credited": 0,
    }
    if not rows:
        return {"ran": True, "checked": 0, **empty}

    stats = {"ran": True, "checked": len(rows), **empty}

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
            # Captured before the signup fields are touched below — the pre-existing-user
            # verdict depends on what we knew BEFORE this pass, not after it.
            signup_seen_by_us = row.signup_status == "SIGNED_UP"

            if match and match.get("user_id") is not None:
                row.eaze_user_id = str(match["user_id"])
                row.signup_status = "SIGNED_UP"
                row.signed_up_at = row.signed_up_at or _parse_timestamp(match.get("registered_at"))
                row.source = "REDASH"
                stats["signups_confirmed"] += 1

                if row.phone_check_status == "UNCHECKED":
                    # The submit-time check never completed (Redash was down), so decide it
                    # now from what we can still distinguish: if our own pipeline recorded
                    # the signup, they registered *after* being referred and the referral is
                    # good. If it never did, this number already belonged to an Eaze account
                    # before anyone referred it — which the Terms exclude.
                    if signup_seen_by_us:
                        row.phone_check_status = "VERIFIED"
                    else:
                        row.phone_check_status = "ALREADY_REGISTERED"
                        row.pre_existing_eaze_user_id = str(match["user_id"])
                        stats["disqualified_already_registered"] += 1
                    row.phone_checked_at = dt.datetime.now(dt.timezone.utc)
            else:
                if row.phone_e164 in unresolved and row.phone_check_status == "UNCHECKED":
                    # No Eaze account for this number — which is exactly what makes it a
                    # valid referral target.
                    row.phone_check_status = "VERIFIED"
                    row.phone_checked_at = dt.datetime.now(dt.timezone.utc)
                if row.phone_e164 in unresolved and row.signup_status == "PENDING":
                    # Not registered yet. Not an error, and re-checked on the next pass.
                    # Guarded on PENDING so this can only fill in an unknown, never
                    # contradict a signup our own pipeline already saw.
                    row.signup_status = "NOT_FOUND"

    # Step 2 — ask about payments. Nobody is paid without this answering yes: a confirmed
    # payment is the only event that releases coins, to either side.
    payable = [
        r
        for r in rows
        if r.eaze_user_id
        and r.phone_check_status != "ALREADY_REGISTERED"
        and (r.referrer_coins_status == "PENDING" or r.signup_coins_status == "PENDING")
    ]
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
                # Confirmed no payment yet. Nobody is owed anything — this is the check
                # working, not a failure. Stays PENDING and is re-checked next pass.
                row.payment_status = "NO_PAYMENT"
                row.last_error = None
                continue

            row.source = "REDASH"
            row.last_error = None
            stats["payments_confirmed"] += 1

            try:
                moved = await _pay_out(session, row, settings, payment, paid_count)
            except Exception:  # noqa: BLE001 - one bad row must not abort the whole pass
                logger.warning("payout failed for %s", row.phone_e164, exc_info=True)
                continue

            if "referred" in moved:
                stats["signup_coins_credited"] += 1
            if "referrer" in moved:
                stats["coins_credited"] += 1

    await _stamp_checked(session, [r.id for r in rows])
    return stats


async def _pay_out(
    session: AsyncSession,
    row: ReferralVerification,
    settings: Settings,
    payment: dict,
    paid_count: int,
) -> list[str]:
    """Hand a confirmed payment to the one crediting path, creating the local records it needs
    if our own pipeline never saw the signup. Returns which sides actually moved coins."""
    referred_user_id = await _ensure_local_user(session, row.phone_e164)
    referral_id = await _ensure_referral(session, row, referred_user_id)
    if referral_id is None:
        # Paid, but no referral can legitimately exist to pay against. Left PENDING so it shows
        # up as outstanding rather than being silently closed.
        return []

    first_at = _parse_timestamp(payment.get("first_payment_at"))
    amount = payment.get("first_payment_amount_paise")
    result = await referral_service.credit_both_on_payment(
        session,
        referral_id=referral_id,
        referrer_user_id=row.referrer_user_id,
        referred_user_id=referred_user_id,
        referred_phone_e164=row.phone_e164,
        settings=settings,
        first_payment_amount_paise=int(amount) if amount is not None else None,
        payment_count=paid_count,
    )
    if first_at is not None:
        await session.execute(
            update(ReferralVerification.__table__)
            .where(ReferralVerification.id == row.id, ReferralVerification.first_payment_at.is_(None))
            .values(first_payment_at=first_at)
        )

    if result["eligible"]:
        failed = result.get("failed", [])
        await update_sheet_status(
            row.phone_e164,
            settings,
            payment="Paid",
            # Never report a side as credited when its wallet call failed — the sheet is what
            # people look at to answer "did they get their coins", so it has to say "failed"
            # rather than quietly showing a payout that never happened.
            friend_coins=(
                "Failed — will retry"
                if "referred" in failed
                else f"Credited {settings.signup_bonus_coins}"
            ),
            referrer_coins=(
                "Failed — will retry"
                if "referrer" in failed
                else f"Credited {settings.recharge_bonus_coins}"
            ),
        )
    return result["credited"]


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
    signup_owed = await session.execute(
        select(func.count()).select_from(ReferralVerification).where(
            ReferralVerification.payment_status == "PAID",
            ReferralVerification.signup_coins_status == "PENDING",
        )
    )
    disqualified = await session.execute(
        select(func.count()).select_from(ReferralVerification).where(
            ReferralVerification.phone_check_status == "ALREADY_REGISTERED"
        )
    )
    unchecked = await session.execute(
        select(func.count()).select_from(ReferralVerification).where(
            ReferralVerification.phone_check_status == "UNCHECKED"
        )
    )
    return {
        "referred": total.scalar_one(),
        "signed_up": signed_up.scalar_one(),
        "paid": paid.scalar_one(),
        "referrer_coins_credited": credited.scalar_one(),
        "paid_but_not_credited": awaiting.scalar_one(),
        "paid_but_signup_coins_not_credited": signup_owed.scalar_one(),
        "disqualified_already_registered": disqualified.scalar_one(),
        "awaiting_phone_check": unchecked.scalar_one(),
    }
