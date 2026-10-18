from datetime import date, datetime

import pytest
from pydantic import ValidationError

from cyclescope.domain.calendar import session_dates
from cyclescope.domain.models import BarBatch, DailyBar, DateRange


def bar(**changes: object) -> DailyBar:
    return DailyBar.model_validate(
        {
            "symbol": "SPY",
            "session_date": "2024-01-02",
            "open": "100",
            "high": "102",
            "low": "99",
            "close": "101",
            "volume": 10,
            **changes,
        }
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"close": "NaN"},
        {"close": "Infinity"},
        {"low": "0"},
        {"open": "-1"},
        {"high": "99"},
        {"low": "101"},
        {"volume": -1},
        {"volume": 1.5},
        {"volume": True},
        {"session_date": None},
        {"session_date": "not-a-date"},
        {"symbol": "spy"},
        {"symbol": "../SPY"},
        {"symbol": "A;DROP"},
    ],
)
def test_bar_validation(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        bar(**changes)


def test_exact_decimal_price() -> None:
    assert str(bar(close="100.12345678").close) == "100.12345678"


@pytest.mark.parametrize(
    "start,end",
    [
        ("2024-01-03", "2024-01-02"),
        ("2000-01-01", "2024-01-01"),
        ("1980-01-01", "1980-01-02"),
        ("2036-01-01", "2036-01-02"),
    ],
)
def test_range_bounds(start: str, end: str) -> None:
    with pytest.raises(ValidationError):
        DateRange.model_validate({"start": start, "end": end})


def test_exchange_calendar_excludes_holidays_not_only_weekends() -> None:
    sessions = session_dates(DateRange(start=date(2024, 1, 12), end=date(2024, 1, 16)))
    assert sessions == (date(2024, 1, 12), date(2024, 1, 16))
    # Good Friday and an extraordinary closure (President Bush memorial).
    assert session_dates(DateRange(start=date(2024, 3, 29), end=date(2024, 3, 29))) == ()
    assert session_dates(DateRange(start=date(2018, 12, 5), end=date(2018, 12, 5))) == ()


def test_timezone_required() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        BarBatch(
            symbol="SPY",
            provider="test",
            data_kind="synthetic",
            data_version="v1",
            fetched_at=datetime(2024, 1, 1),
            bars=(bar(),),
        )
