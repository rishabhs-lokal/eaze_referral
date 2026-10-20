"""When referral coins are allowed to leave the building.

Coins are credited only inside a short nightly window — by default the first 30 minutes of the
IST day. Everything else about the pipeline is unchanged: payments are still confirmed against
Redash every pass, statuses still advance promptly, dashboards still read true the moment a
payment lands. The only thing that waits is the call to the coin API.

The reason is the shared free-coins endpoint. Every Lokal tool credits through it, and a user
granted coins twice in one day is the case that misbehaves. Paying at the very start of the IST
day puts this service first, before any other tool has granted anything that day — which avoids
the collision by construction rather than by detecting it after the fact.

Lives in its own module because `verification` imports `referral_service` and both need this;
putting it in either would make that cycle.

TIMEZONE, STATED EXPLICITLY, BECAUSE THIS IS WHERE THIS CODEBASE HAS BEEN BITTEN BEFORE: the
window is defined in its own timezone, not the pod's and not the warehouse's. Containers run
UTC, so 00:00 IST is 18:30 UTC the PREVIOUS day. Comparing a UTC wall clock against a
"midnight" that was never converted would open the window at 05:30 IST and look entirely
plausible while doing it.
"""

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from app.config import Settings

logger = logging.getLogger("eaze_referral.payout_window")


def _zone(settings: Settings) -> ZoneInfo | dt.tzinfo:
    try:
        return ZoneInfo(settings.payout_window_timezone)
    except Exception:
        # A bad timezone must not stop payouts entirely — falling back to UTC shifts the window
        # rather than closing it forever, and says so loudly.
        logger.warning(
            "unknown PAYOUT_WINDOW_TIMEZONE %r, falling back to UTC",
            settings.payout_window_timezone,
        )
        return dt.timezone.utc


def _start_hour_minute(settings: Settings) -> tuple[int, int]:
    raw = (settings.payout_window_start or "00:00").strip()
    try:
        hour_s, minute_s = raw.split(":", 1)
        hour, minute = int(hour_s), int(minute_s)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(raw)
        return hour, minute
    except ValueError:
        logger.warning("unparseable PAYOUT_WINDOW_START %r, using 00:00", raw)
        return 0, 0


def is_enabled(settings: Settings) -> bool:
    """A window of zero minutes means no window: credit whenever a payment is confirmed, which
    is how this service behaved before the window existed."""
    return settings.payout_window_minutes > 0


def window_for(now: dt.datetime, settings: Settings) -> tuple[dt.datetime, dt.datetime]:
    """The window containing or most recently preceding `now`, as aware datetimes."""
    zone = _zone(settings)
    hour, minute = _start_hour_minute(settings)
    local = now.astimezone(zone)
    start = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if start > local:
        # Today's window has not opened yet, so the relevant one began yesterday. Matters for a
        # start time other than midnight; harmless at 00:00.
        start -= dt.timedelta(days=1)
    return start, start + dt.timedelta(minutes=settings.payout_window_minutes)


def is_open(now: dt.datetime, settings: Settings) -> bool:
    """Whether coins may be credited at `now`. Always true when the window is disabled."""
    if not is_enabled(settings):
        return True
    start, end = window_for(now, settings)
    return start <= now.astimezone(start.tzinfo) < end


def next_open(now: dt.datetime, settings: Settings) -> dt.datetime:
    """When the window next opens, for the scheduler to align its sleep to.

    Returns `now` while the window is already open, so a caller never sleeps through one it is
    standing in.
    """
    if not is_enabled(settings) or is_open(now, settings):
        return now
    start, _end = window_for(now, settings)
    return start + dt.timedelta(days=1)


def seconds_until_open(now: dt.datetime, settings: Settings) -> float:
    """Never negative. Zero means the window is open right now."""
    target = next_open(now, settings)
    return max(0.0, (target - now.astimezone(target.tzinfo)).total_seconds())


def describe(settings: Settings) -> str:
    if not is_enabled(settings):
        return "payout window disabled (credit on confirmation)"
    hour, minute = _start_hour_minute(settings)
    return (
        f"payout window {hour:02d}:{minute:02d}"
        f"-{settings.payout_window_minutes}min {settings.payout_window_timezone}"
    )
