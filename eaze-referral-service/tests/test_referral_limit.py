"""The per-referrer referral cap, against a real Postgres.

These run the actual submit_intents against a real database rather than mocking the session,
because every interesting property of the cap is a database property: the slot count is a join,
the race protection is a row lock, and the partial-fill behaviour depends on inserts and their
ON CONFLICT outcomes happening in order inside one transaction. A mocked session would assert
that the code calls the functions it calls, which is not the question.

Skipped entirely when TEST_DATABASE_URL is unset, so the suite still runs without a database.
"""

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.models import Base, ReferralIntent, ReferralVerification, User
from app.services import referral_service

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set; cap tests need a real Postgres"
)


def _settings(limit: int = 3) -> Settings:
    return Settings(
        database_url=TEST_DATABASE_URL or "",
        signup_bonus_coins=1000,
        recharge_bonus_coins=1000,
        max_referrals_per_user=limit,
    )


# A fresh block of valid Indian mobile numbers per call, so repeated runs never collide on
# referral_intents' UNIQUE phone_e164 — and so a failed run leaving rows behind cannot make the
# next one pass or fail for the wrong reason. 6000000000-9999999999 is exactly the range
# is_valid_indian_e164 accepts; the headroom keeps base + n inside it.
def _phones(n: int) -> list[str]:
    base = 6_000_000_000 + (uuid.uuid4().int % (3_000_000_000 - 100))
    return [f"+91{base + i}" for i in range(n)]


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(
        (TEST_DATABASE_URL or "").replace("postgresql://", "postgresql+asyncpg://"), echo=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def referrer(session: AsyncSession) -> User:
    user = User(phone_e164=_phones(1)[0], external_ref=f"test-{uuid.uuid4().hex[:12]}")
    session.add(user)
    await session.commit()
    return user


async def test_saves_up_to_the_limit_and_refuses_the_rest(session, referrer):
    phones = _phones(5)
    saved, skipped, used, limit = await referral_service.submit_intents(
        session, referrer, phones, _settings(3)
    )

    assert saved == 3
    assert used == 3
    assert limit == 3
    over = [s for s in skipped if s["reason"] == "referral_limit_reached"]
    assert len(over) == 2
    # The first three submitted are the ones kept — order is the referrer's own priority, and
    # silently saving a different subset than the one at the top of their list would be worse
    # than refusing the whole submission.
    assert [s["phone"] for s in over] == phones[3:]


async def test_limit_is_cumulative_across_separate_submissions(session, referrer):
    phones = _phones(4)
    first, _, used_after_first, _ = await referral_service.submit_intents(
        session, referrer, phones[:2], _settings(3)
    )
    assert (first, used_after_first) == (2, 2)

    # One slot left, two numbers offered: the first lands, the second does not. A cap that only
    # looked at the current request would accept both.
    second, skipped, used, _ = await referral_service.submit_intents(
        session, referrer, phones[2:], _settings(3)
    )
    assert second == 1
    assert used == 3
    assert [s["reason"] for s in skipped] == ["referral_limit_reached"]


async def test_an_exhausted_referrer_saves_nothing(session, referrer):
    settings = _settings(3)
    await referral_service.submit_intents(session, referrer, _phones(3), settings)

    saved, skipped, used, _ = await referral_service.submit_intents(
        session, referrer, _phones(1), settings
    )
    assert saved == 0
    assert used == 3
    assert skipped[0]["reason"] == "referral_limit_reached"


async def test_rejected_numbers_never_consume_a_slot(session, referrer):
    """Everything rejected by an earlier gate has to be free, or the cap punishes people for
    mistakes that produced no referral: a typo, or a friend who turns out to be on Eaze already."""
    settings = _settings(3)
    good = _phones(1)[0]
    saved, skipped, used, _ = await referral_service.submit_intents(
        session,
        referrer,
        ["+919999999999", "not-a-number", referrer.phone_e164, good],
        settings,
    )

    assert saved == 1
    assert used == 1, "only the one accepted number spent a slot"
    reasons = {s["reason"] for s in skipped}
    assert "referral_limit_reached" not in reasons


async def test_a_number_later_found_already_registered_releases_its_slot(session, referrer):
    """The one refund. The synchronous check at save time is time-boxed and gives up rather than
    hanging the Save button, so this verdict routinely lands minutes later — by which point the
    referrer has already been charged for a referral that can never pay."""
    settings = _settings(3)
    phones = _phones(3)
    await referral_service.submit_intents(session, referrer, phones, settings)
    assert await referral_service.count_referral_slots_used(session, referrer.id) == 3

    await session.execute(
        update(ReferralVerification.__table__)
        .where(ReferralVerification.phone_e164 == phones[0])
        .values(phone_check_status="ALREADY_REGISTERED")
    )
    await session.commit()

    assert await referral_service.count_referral_slots_used(session, referrer.id) == 2
    saved, _, used, _ = await referral_service.submit_intents(
        session, referrer, _phones(1), settings
    )
    assert saved == 1
    assert used == 3


async def test_expired_and_unconverted_referrals_keep_their_slot(session, referrer):
    """The explicit non-refund. Three picks that went nowhere is the outcome a cap is for — if
    dead referrals released slots the limit would be unbounded for anyone patient enough."""
    settings = _settings(3)
    phones = _phones(3)
    await referral_service.submit_intents(session, referrer, phones, settings)

    await session.execute(
        update(ReferralVerification.__table__)
        .where(ReferralVerification.phone_e164.in_(phones))
        .values(signup_status="NOT_FOUND", referrer_coins_status="EXPIRED")
    )
    await session.execute(
        update(ReferralIntent.__table__)
        .where(ReferralIntent.phone_e164.in_(phones))
        .values(status="EXPIRED")
    )
    await session.commit()

    assert await referral_service.count_referral_slots_used(session, referrer.id) == 3
    saved, skipped, _, _ = await referral_service.submit_intents(
        session, referrer, _phones(1), settings
    )
    assert saved == 0
    assert skipped[0]["reason"] == "referral_limit_reached"


async def test_concurrent_submissions_cannot_exceed_the_limit(session, referrer):
    """Two tabs pressing Save at the same instant. Without the FOR UPDATE on the referrer's row
    both transactions read the same slot count, both conclude they have room, and the referrer
    ends up over the cap — a read-modify-write race that no amount of care in the loop fixes."""
    engine = create_async_engine(
        (TEST_DATABASE_URL or "").replace("postgresql://", "postgresql+asyncpg://")
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    settings = _settings(3)

    async def submit(phones: list[str]):
        async with maker() as s:
            fresh = (await s.execute(select(User).where(User.id == referrer.id))).scalar_one()
            return await referral_service.submit_intents(s, fresh, phones, settings)

    batches = [_phones(2), _phones(2), _phones(2)]
    results = await asyncio.gather(*(submit(b) for b in batches))
    await engine.dispose()

    assert sum(r[0] for r in results) == 3, "six numbers offered concurrently, three slots"
    assert await referral_service.count_referral_slots_used(session, referrer.id) == 3


async def test_limit_of_zero_turns_the_programme_off(session, referrer):
    saved, skipped, used, limit = await referral_service.submit_intents(
        session, referrer, _phones(1), _settings(0)
    )
    assert (saved, used, limit) == (0, 0, 0)
    assert skipped[0]["reason"] == "referral_limit_reached"


async def test_a_referrer_already_over_the_limit_keeps_what_they_have(session, referrer):
    """Existing referrers when the cap ships. Nobody loses a referral they already made; they
    simply cannot add more, and the count reads at-or-over rather than going negative."""
    settings = _settings(3)
    await referral_service.submit_intents(session, referrer, _phones(5), _settings(5))
    assert await referral_service.count_referral_slots_used(session, referrer.id) == 5

    saved, skipped, used, limit = await referral_service.submit_intents(
        session, referrer, _phones(1), settings
    )
    assert saved == 0
    assert (used, limit) == (5, 3)
    assert skipped[0]["reason"] == "referral_limit_reached"
