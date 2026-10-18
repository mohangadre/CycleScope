from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import cast
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from cyclescope.domain.errors import InsufficientData
from cyclescope.domain.models import DateRange


@lru_cache(maxsize=1)
def _calendar() -> xcals.ExchangeCalendar:
    # Fixed coverage avoids host-date-dependent calendar bounds.
    return xcals.get_calendar("XNYS", start="1990-01-01", end="2035-12-31")


def session_dates(period: DateRange) -> tuple[date, ...]:
    """US equity session dates, including holidays and extraordinary closures."""
    return tuple(stamp.date() for stamp in _calendar().sessions_in_range(period.start, period.end))


def session_on_or_before(day: date) -> date:
    DateRange(start=day, end=day)
    return cast(date, _calendar().date_to_session(day, direction="previous").date())


def completed_session_before_today(now: datetime) -> date:
    """Conservatively exclude the current New York day's potentially partial bar."""
    if now.utcoffset() is None:
        raise ValueError("An aware timestamp is required")
    yesterday = now.astimezone(ZoneInfo("America/New_York")).date() - timedelta(days=1)
    return session_on_or_before(yesterday)


def future_sessions(origin: date, count: int) -> tuple[date, ...]:
    if not 1 <= count <= 126:
        raise InsufficientData("Forecast horizon must be 1–126 trading sessions")
    calendar = _calendar()
    index = calendar.sessions.get_indexer([str(origin)])[0]
    if index < 0:
        raise InsufficientData("Forecast origin must be an exchange session")
    sessions = calendar.sessions[index + 1 : index + 1 + count]
    if len(sessions) != count:
        raise InsufficientData("Forecast extends beyond supported exchange calendar")
    return tuple(stamp.date() for stamp in sessions)


def trailing_sessions(as_of: date, count: int) -> tuple[date, ...]:
    """An exact exchange-session window ending at/before the requested cutoff."""
    if not 1 <= count <= 2520:
        raise InsufficientData("History must contain 1–2520 trading sessions")
    origin = session_on_or_before(as_of)
    calendar = _calendar()
    index = int(calendar.sessions.get_indexer([str(origin)])[0])
    if index + 1 < count:
        raise InsufficientData("History starts before the supported exchange calendar")
    return tuple(stamp.date() for stamp in calendar.sessions[index + 1 - count : index + 1])
