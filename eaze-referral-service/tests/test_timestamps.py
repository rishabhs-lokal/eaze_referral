"""Regression tests for _parse_timestamp.

This function took down a production reconcile pass. Redash serialises without an offset
(`2026-07-28T06:43:06.898`); every column it gets compared against is DateTime(timezone=True)
and therefore aware; comparing the two raises TypeError. The crash sat in the branch that only
runs once a referral has a payment row, so an empty database and every local test walked
straight past it.

The rule these tests pin down is simple and total: whatever goes in, what comes out is aware or
None. Never naive, so a comparison can never raise again.
"""

import datetime as dt

from app.services.verification import _parse_timestamp

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def test_naive_string_becomes_aware():
    # The exact shape the warehouse returned for the account that crashed the pass.
    got = _parse_timestamp("2026-07-28T06:43:06.898", "Asia/Kolkata")
    assert got is not None
    assert got.tzinfo is not None
    assert got.utcoffset() == dt.timedelta(hours=5, minutes=30)


def test_comparison_against_an_aware_column_does_not_raise():
    """The actual production failure, reduced: `registered_at < row.created_at`."""
    registered_at = _parse_timestamp("2026-07-28T06:43:06.898", "Asia/Kolkata")
    created_at = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.timezone.utc)
    assert registered_at < created_at  # would have been TypeError before


def test_offset_already_present_is_left_alone():
    got = _parse_timestamp("2026-07-28T06:43:06.898+05:30", "UTC")
    assert got.utcoffset() == dt.timedelta(hours=5, minutes=30)


def test_z_suffix_is_utc():
    got = _parse_timestamp("2026-07-28T06:43:06.898Z", "Asia/Kolkata")
    assert got.utcoffset() == dt.timedelta(0)


def test_naive_datetime_object_is_also_made_aware():
    """Some warehouse drivers hand back a datetime rather than a string. The previous version
    returned those untouched, which is how a naive value reached the comparison."""
    got = _parse_timestamp(dt.datetime(2026, 7, 28, 6, 43), "Asia/Kolkata")
    assert got.tzinfo is not None


def test_none_and_garbage_stay_none():
    assert _parse_timestamp(None, "Asia/Kolkata") is None
    assert _parse_timestamp("not a date", "Asia/Kolkata") is None
    assert _parse_timestamp("", "Asia/Kolkata") is None


def test_unknown_timezone_falls_back_to_utc_rather_than_raising():
    """A bad DB_TIMEZONE must not be able to stop payouts — the whole point of this function
    is that no input takes the pass down."""
    got = _parse_timestamp("2026-07-28T06:43:06.898", "Not/AZone")
    assert got is not None
    assert got.utcoffset() == dt.timedelta(0)


def test_warehouse_naive_is_read_as_utc_not_ist():
    """The six-hour mistake that would have denied the first real payout.

    The warehouse returned registered_at 2026-10-12T11:49:25 for an account created 26 minutes
    before the wall clock read 12:15 UTC. Read as IST that lands at 06:19 UTC — hours before the
    referral that produced it — and the pre-existing-user guard denies both sides their coins.
    """
    as_utc = _parse_timestamp("2026-10-12T11:49:25.635", "UTC")
    as_ist = _parse_timestamp("2026-10-12T11:49:25.635", "Asia/Kolkata")
    assert as_utc.astimezone(dt.timezone.utc).hour == 11
    assert as_ist.astimezone(dt.timezone.utc).hour == 6
    # A referral created at 11:30 UTC, with the signup at 11:49 UTC: genuinely new.
    created_at = dt.datetime(2026, 10, 12, 11, 30, tzinfo=dt.timezone.utc)
    assert as_utc > created_at, "UTC reading keeps a genuine new signup eligible"
    assert as_ist < created_at, "the IST reading is what would have disqualified it"
