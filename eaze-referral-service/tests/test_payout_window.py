"""The nightly payout window.

The window decides when real coins leave the building, and it is defined in IST while the pods
run UTC — 00:00 IST is 18:30 UTC the PREVIOUS day. A comparison that forgets the conversion
opens the window at 05:30 IST and looks completely plausible doing it. That class of mistake has
already cost this codebase one near-miss on a real payout, so every boundary here is pinned
against an explicit UTC instant rather than against "now".
"""

import datetime as dt

import pytest

from app.config import Settings
from app.services import payout_window

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _settings(**over) -> Settings:
    base = dict(signup_bonus_coins=1000, recharge_bonus_coins=1000)
    base.update(over)
    return Settings(**base)


def _utc(y, m, d, h, mi) -> dt.datetime:
    return dt.datetime(y, m, d, h, mi, tzinfo=dt.timezone.utc)


def test_default_window_is_the_first_half_hour_of_the_ist_day():
    s = _settings()
    assert s.payout_window_start == "00:00"
    assert s.payout_window_minutes == 30
    assert s.payout_window_timezone == "Asia/Kolkata"


@pytest.mark.parametrize(
    "utc_instant, expected_open, why",
    [
        # 00:00 IST == 18:30 UTC the previous day. This is the whole point of the module.
        (_utc(2026, 10, 19, 18, 30), True, "exactly window open"),
        (_utc(2026, 10, 19, 18, 45), True, "15 min in"),
        (_utc(2026, 10, 19, 18, 59), True, "29 min in, last open minute"),
        (_utc(2026, 10, 19, 19, 0), False, "30 min in, window has closed"),
        (_utc(2026, 10, 19, 18, 29), False, "one minute before it opens"),
        # Midday and evening IST must never be open.
        (_utc(2026, 10, 19, 6, 30), False, "12:00 IST"),
        (_utc(2026, 10, 19, 12, 0), False, "17:30 IST"),
        # The naive-UTC trap: 00:00 UTC is 05:30 IST, firmly outside the window. A version that
        # compared the UTC clock against "midnight" would call this open.
        (_utc(2026, 10, 19, 0, 0), False, "00:00 UTC is 05:30 IST, NOT the window"),
        (_utc(2026, 10, 19, 0, 15), False, "00:15 UTC is 05:45 IST, NOT the window"),
    ],
)
def test_window_open_only_inside_the_ist_half_hour(utc_instant, expected_open, why):
    assert payout_window.is_open(utc_instant, _settings()) is expected_open, why


def test_zero_minutes_disables_the_window_entirely():
    """The escape hatch: credit on confirmation, as the service behaved before the window."""
    s = _settings(payout_window_minutes=0)
    assert payout_window.is_enabled(s) is False
    for hour in range(0, 24, 3):
        assert payout_window.is_open(_utc(2026, 10, 19, hour, 0), s) is True


def test_next_open_is_tonight_not_last_night():
    s = _settings()
    # 10:00 IST on the 20th -> the next window is 00:00 IST on the 21st.
    now = _utc(2026, 10, 20, 4, 30)
    nxt = payout_window.next_open(now, s)
    assert nxt > now
    assert nxt.astimezone(IST).hour == 0
    assert nxt.astimezone(IST).minute == 0
    assert nxt.astimezone(IST).day == 21


def test_next_open_returns_now_while_the_window_is_open():
    """A caller must never sleep through a window it is standing in."""
    s = _settings()
    now = _utc(2026, 10, 19, 18, 40)  # 00:10 IST
    assert payout_window.next_open(now, s) == now
    assert payout_window.seconds_until_open(now, s) == 0.0


def test_seconds_until_open_is_never_negative():
    s = _settings()
    for hour in range(24):
        for minute in (0, 29, 30, 31, 59):
            got = payout_window.seconds_until_open(_utc(2026, 10, 19, hour, minute), s)
            assert got >= 0.0


def test_seconds_until_open_is_under_a_day():
    """A wait longer than 24h would mean the boundary maths slipped a day — payouts would stall
    for a full extra cycle and the only symptom would be silence."""
    s = _settings()
    for hour in range(24):
        got = payout_window.seconds_until_open(_utc(2026, 10, 19, hour, 7), s)
        assert got <= 24 * 3600


def test_a_non_midnight_window_still_works():
    """The window is configurable, so the maths must not secretly assume midnight."""
    s = _settings(payout_window_start="02:15", payout_window_minutes=10)
    # 02:15 IST == 20:45 UTC previous day.
    assert payout_window.is_open(_utc(2026, 10, 19, 20, 45), s) is True
    assert payout_window.is_open(_utc(2026, 10, 19, 20, 54), s) is True
    assert payout_window.is_open(_utc(2026, 10, 19, 20, 55), s) is False
    assert payout_window.is_open(_utc(2026, 10, 19, 20, 44), s) is False


def test_unknown_timezone_falls_back_to_utc_rather_than_raising():
    """A typo in the timezone must shift the window, never stop payouts outright."""
    s = _settings(payout_window_timezone="Not/AZone")
    assert payout_window.is_open(_utc(2026, 10, 19, 0, 5), s) is True  # UTC midnight
    assert payout_window.is_open(_utc(2026, 10, 19, 12, 0), s) is False


def test_unparseable_start_falls_back_to_midnight():
    s = _settings(payout_window_start="banana")
    assert payout_window.is_open(_utc(2026, 10, 19, 18, 35), s) is True  # 00:05 IST


def test_describe_names_the_window_for_the_logs():
    assert "00:00" in payout_window.describe(_settings())
    assert "disabled" in payout_window.describe(_settings(payout_window_minutes=0))


# --- scheduler behaviour: the loop runs ONLY inside the window ---------------------------------


def test_scheduler_sleeps_through_the_whole_day_to_the_next_window():
    """The 15-minute all-day cadence is gone. Closed, the loop waits for the opening rather
    than waking repeatedly to discover it still cannot pay anyone."""
    import unittest.mock as mock

    from app.services import scheduler

    s = _settings()

    class At(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _utc(2026, 10, 19, 6, 30)  # 12:00 IST, mid-afternoon in the window's day

    with mock.patch.object(scheduler.dt, "datetime", At):
        slept = scheduler._sleep_seconds(s)

    # 12:00 IST -> 00:00 IST is 12 hours away, and must be ONE sleep, not 48 ticks.
    assert slept == pytest.approx(12 * 3600, abs=60)
    assert slept > settings_interval(s), "must not fall back to the old interval"


def settings_interval(s: Settings) -> float:
    return float(s.reconcile_interval_seconds)


def test_scheduler_ticks_at_the_interval_while_the_window_is_open():
    """Inside the window several passes should fit, so the queue drains rather than getting one
    shot a night."""
    import unittest.mock as mock

    from app.services import scheduler

    s = _settings()

    class At(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _utc(2026, 10, 19, 18, 35)  # 00:05 IST, window open

    with mock.patch.object(scheduler.dt, "datetime", At):
        assert scheduler._sleep_seconds(s) == settings_interval(s)


def test_scheduler_waits_for_an_imminent_window_rather_than_stepping_over_it():
    """The restart case the alignment exists for: a fixed interval from 23:50 IST would next
    fire at 00:05 — inside the window by luck — but from 00:29 it would fire at 00:44, with the
    window closed and a day of payouts stranded."""
    import unittest.mock as mock

    from app.services import scheduler

    s = _settings()

    class At(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _utc(2026, 10, 19, 18, 20)  # 23:50 IST, 10 min before open

    with mock.patch.object(scheduler.dt, "datetime", At):
        assert scheduler._sleep_seconds(s) == pytest.approx(600, abs=5)


def test_scheduler_keeps_the_plain_interval_when_the_window_is_disabled():
    import unittest.mock as mock

    from app.services import scheduler

    s = _settings(payout_window_minutes=0)

    class At(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _utc(2026, 10, 19, 6, 30)

    with mock.patch.object(scheduler.dt, "datetime", At):
        assert scheduler._sleep_seconds(s) == settings_interval(s)
