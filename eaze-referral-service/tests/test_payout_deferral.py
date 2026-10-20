"""A deferred payout must not be recorded as a completed one.

This is the dangerous half of the payout window. Outside the window nothing is sent to the coin
API — and the pre-existing code marked a side CREDITED whenever it was not in `failures`, which
a deferred payout satisfies trivially: it has no failures because it never tried. Left alone,
every payment confirmed outside the window would have been stamped CREDITED and REWARDED, left
the reconciler's queue, and reported "Credited 1000" into the sheet, while no coins moved and
nothing errored anywhere.

So these tests assert the absence of a payout, which is the only direction that can lose money
silently.
"""

import datetime as dt
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.models import Base, Referral, ReferralVerification, User, WalletTransaction
from app.services import referral_service

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set; these need a real Postgres"
)


def _settings(**over) -> Settings:
    base = dict(
        database_url=TEST_DATABASE_URL or "",
        signup_bonus_coins=1000,
        recharge_bonus_coins=1000,
    )
    base.update(over)
    return Settings(**base)


def _phone() -> str:
    return f"+91{6_000_000_000 + (uuid.uuid4().int % 3_000_000_000)}"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(
        (TEST_DATABASE_URL or "").replace("postgresql://", "postgresql+asyncpg://")
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _referral(session: AsyncSession) -> tuple[int, int, int, str]:
    """A signed-up referral ready to be paid. Returns (referral_id, referrer_id, referred_id, phone)."""
    referrer = User(phone_e164=_phone(), external_ref=f"ref-{uuid.uuid4().hex[:10]}")
    referred = User(phone_e164=_phone())
    session.add_all([referrer, referred])
    await session.flush()

    referral = Referral(
        referrer_user_id=referrer.id,
        referred_user_id=referred.id,
        referred_phone_e164=referred.phone_e164,
        referral_intent_id=None,
        status="SIGNED_UP",
    )
    # referral_intent_id is NOT NULL in the schema; create the intent the honest way.
    from app.models import ReferralIntent

    intent = ReferralIntent(referrer_user_id=referrer.id, phone_e164=referred.phone_e164)
    session.add(intent)
    await session.flush()
    referral.referral_intent_id = intent.id
    session.add(referral)
    await session.flush()

    session.add(
        ReferralVerification(
            phone_e164=referred.phone_e164,
            referrer_user_id=referrer.id,
            referrer_external_id=referrer.external_ref,
            referral_intent_id=intent.id,
            referral_id=referral.id,
            eaze_user_id=f"eaze-{uuid.uuid4().hex[:8]}",
            signup_status="SIGNED_UP",
        )
    )
    await session.commit()
    return referral.id, referrer.id, referred.id, referred.phone_e164


async def _credit(session, settings, ids) -> dict:
    referral_id, referrer_id, referred_id, phone = ids
    return await referral_service.credit_both_on_payment(
        session,
        referral_id=referral_id,
        referrer_user_id=referrer_id,
        referred_user_id=referred_id,
        referred_phone_e164=phone,
        settings=settings,
    )


# The window is derived from the real clock, so these two settings stand in for "now is outside"
# and "now is inside" without having to freeze time: a zero-length window is never open, and a
# full-day window always is.
CLOSED = dict(payout_window_start="00:00", payout_window_minutes=1, payout_window_timezone="UTC")
ALWAYS_OPEN = dict(payout_window_minutes=0)


def _closed_now() -> dict:
    """A one-minute window positioned so it cannot contain the current instant."""
    now = dt.datetime.now(dt.timezone.utc)
    far = (now + dt.timedelta(hours=12)).strftime("%H:%M")
    return dict(payout_window_start=far, payout_window_minutes=1, payout_window_timezone="UTC")


async def test_outside_the_window_nothing_is_credited(session):
    ids = await _referral(session)
    result = await _credit(session, _settings(**_closed_now()), ids)
    await session.commit()

    assert result["eligible"] is True
    assert result["deferred"] is True
    assert result["credited"] == []
    assert result["failed"] == []


async def test_outside_the_window_no_ledger_row_is_claimed(session):
    """The ledger is the idempotency key. A row claimed now but never sent would permanently
    block the real payout, because the retry would see it and skip."""
    ids = await _referral(session)
    referral_id = ids[0]
    await _credit(session, _settings(**_closed_now()), ids)
    await session.commit()

    rows = await session.execute(
        select(WalletTransaction).where(WalletTransaction.reference_id == referral_id)
    )
    assert rows.scalars().all() == []


async def test_outside_the_window_coin_statuses_stay_pending(session):
    """PENDING is what keeps the row in the reconciler's queue. CREDITED would remove it
    forever, and nothing would ever retry."""
    ids = await _referral(session)
    phone = ids[3]
    await _credit(session, _settings(**_closed_now()), ids)
    await session.commit()

    row = (
        await session.execute(
            select(ReferralVerification).where(ReferralVerification.phone_e164 == phone)
        )
    ).scalar_one()
    assert row.referrer_coins_status == "PENDING"
    assert row.signup_coins_status == "PENDING"
    # The payment is still recorded — it is true whenever it happened.
    assert row.payment_status == "PAID"
    assert "payout window" in (row.last_error or "")


async def test_outside_the_window_the_referral_is_not_marked_rewarded(session):
    ids = await _referral(session)
    referral_id = ids[0]
    await _credit(session, _settings(**_closed_now()), ids)
    await session.commit()

    referral = (
        await session.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one()
    assert referral.status != "REWARDED"


async def test_outside_the_window_no_wallet_balance_moves(session):
    ids = await _referral(session)
    _, referrer_id, referred_id, _ = ids
    await _credit(session, _settings(**_closed_now()), ids)
    await session.commit()

    for user_id in (referrer_id, referred_id):
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        assert user.wallet_balance == 0


async def test_inside_the_window_the_payout_completes(session):
    """The other direction: with the window open the behaviour is exactly as before. The coin
    API is unconfigured here, so _hand_coins_to_eaze is a no-op and the ledger is the proof."""
    ids = await _referral(session)
    referral_id, referrer_id, referred_id, phone = ids
    result = await _credit(session, _settings(**ALWAYS_OPEN), ids)
    await session.commit()

    assert result["deferred"] is False
    assert set(result["credited"]) == {"referred", "referrer"}

    rows = (
        await session.execute(
            select(WalletTransaction).where(WalletTransaction.reference_id == referral_id)
        )
    ).scalars().all()
    assert len(rows) == 2

    row = (
        await session.execute(
            select(ReferralVerification).where(ReferralVerification.phone_e164 == phone)
        )
    ).scalar_one()
    assert row.referrer_coins_status == "CREDITED"
    assert row.signup_coins_status == "CREDITED"


async def test_a_deferred_payout_is_paid_once_the_window_opens(session):
    """The whole promise: deferral delays a payout, it does not lose one."""
    ids = await _referral(session)
    referral_id = ids[0]

    deferred = await _credit(session, _settings(**_closed_now()), ids)
    await session.commit()
    assert deferred["deferred"] is True

    later = await _credit(session, _settings(**ALWAYS_OPEN), ids)
    await session.commit()
    assert later["deferred"] is False
    assert set(later["credited"]) == {"referred", "referrer"}

    rows = (
        await session.execute(
            select(WalletTransaction).where(WalletTransaction.reference_id == referral_id)
        )
    ).scalars().all()
    assert len(rows) == 2, "exactly one credit per side, not two"


async def test_the_window_does_not_double_pay_across_passes(session):
    """Idempotency still holds with the window in play — several open passes move coins once."""
    ids = await _referral(session)
    referral_id = ids[0]
    for _ in range(3):
        await _credit(session, _settings(**ALWAYS_OPEN), ids)
        await session.commit()

    rows = (
        await session.execute(
            select(WalletTransaction).where(WalletTransaction.reference_id == referral_id)
        )
    ).scalars().all()
    assert len(rows) == 2
