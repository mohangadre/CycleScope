from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from cyclescope.api.app import create_app
from cyclescope.domain.calendar import completed_session_before_today, session_dates
from cyclescope.domain.models import DateRange
from cyclescope.providers.alpaca import AlpacaProvider
from cyclescope.providers.synthetic import SyntheticProvider
from cyclescope.services.ingestion import ingest
from cyclescope.storage.models import DailyBarRow, IngestionRunRow

pytestmark = pytest.mark.postgres
PERIOD = {"start": "2024-01-02", "end": "2024-01-04"}


def mock_provider(calls: list[httpx.Request], status: int = 200) -> AlpacaProvider:
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if status != 200:
            return httpx.Response(status, text="private provider diagnostic")
        symbol = request.url.path.split("/")[-2]
        interval = DateRange(
            start=date.fromisoformat(request.url.params["start"][:10]),
            end=date.fromisoformat(request.url.params["end"][:10]),
        )
        # Invented external-provider test observations; never public market evidence.
        bars = [
            {
                "t": datetime.combine(day, time.min, ZoneInfo("America/New_York")).isoformat(),
                "o": 100 + i,
                "h": 101 + i,
                "l": 99 + i,
                "c": 100 + i,
                "v": 1000,
            }
            for i, day in enumerate(session_dates(interval))
        ]
        return httpx.Response(200, json={"symbol": symbol, "bars": bars, "next_page_token": None})

    return AlpacaProvider("test-key", "test-secret", transport=httpx.MockTransport(handle))


def test_coverage_is_source_specific_and_reads_never_fetch(db: Engine) -> None:
    ingest(db, SyntheticProvider(), "SPY", DateRange.model_validate(PERIOD))
    calls: list[httpx.Request] = []
    with TestClient(create_app(engine=db, provider=mock_provider(calls))) as client:
        body = client.get("/api/v1/prices/SPY/coverage").json()
        assert body["provider"] == "alpaca-iex"
        assert body["data_kind"] == "real"
        assert body["session_count"] == 0
        assert body["first_session"] is body["last_session"] is None
        assert calls == []


def test_explicit_refresh_fills_range_and_preserves_audit_history(db: Engine) -> None:
    calls: list[httpx.Request] = []
    with TestClient(create_app(engine=db, provider=mock_provider(calls))) as client:
        first = client.post("/api/v1/prices/SPY/refresh", json=PERIOD)
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["data_kind"] == "real"
        assert body["coverage"]["session_count"] == 3
        assert body["coverage"]["first_session"] == "2024-01-02"
        assert body["coverage"]["last_session"] == "2024-01-04"
        assert calls[0].url.host == "data.alpaca.markets"
        assert calls[0].url.params["feed"] == "iex"
        assert calls[0].url.params["adjustment"] == "all"
        prices = client.get("/api/v1/prices/SPY", params=PERIOD).json()
        assert [bar["close"] for bar in prices["bars"]] == [
            "100.00000000",
            "101.00000000",
            "102.00000000",
        ]
        again = client.post("/api/v1/prices/SPY/refresh", json=PERIOD).json()
        assert again["ingestion_run_id"] != body["ingestion_run_id"]
        assert client.get("/api/v1/prices/SPY/coverage").json()["session_count"] == 3
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(DailyBarRow)) == 3
        assert session.scalar(select(func.count()).select_from(IngestionRunRow)) == 2


@pytest.mark.parametrize("status", [401, 403, 429])
def test_refresh_provider_failure_does_not_seed_or_partially_write(db: Engine, status: int) -> None:
    calls: list[httpx.Request] = []
    with TestClient(create_app(engine=db, provider=mock_provider(calls, status))) as client:
        response = client.post("/api/v1/prices/SPY/refresh", json=PERIOD)
        assert response.status_code == 503
        assert str(status) in response.json()["error"]["message"]
        assert "private" not in response.text
        assert client.get("/api/v1/prices/SPY/coverage").json()["session_count"] == 0
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(IngestionRunRow)) == 0


@pytest.mark.parametrize(
    "period",
    [
        {"start": "2024-01-04", "end": "2024-01-02"},
        {"start": "2024-01-06", "end": "2024-01-07"},
        {"start": "2035-01-02", "end": "2035-01-03"},
        {"start": "2000-01-01", "end": "2024-01-04"},
    ],
)
def test_invalid_empty_or_future_ranges_do_not_call_provider(
    db: Engine, period: dict[str, str]
) -> None:
    calls: list[httpx.Request] = []
    with TestClient(create_app(engine=db, provider=mock_provider(calls))) as client:
        assert client.post("/api/v1/prices/SPY/refresh", json=period).status_code == 422
    assert calls == []


def test_synthetic_unknown_symbol_and_capacity_are_explicit(db: Engine) -> None:
    with TestClient(create_app(engine=db, provider=SyntheticProvider())) as client:
        assert client.post("/api/v1/prices/SPY/refresh", json=PERIOD).status_code == 422
    calls: list[httpx.Request] = []
    app = create_app(engine=db, provider=mock_provider(calls))
    with TestClient(app) as client:
        assert client.post("/api/v1/prices/UNKNOWN/refresh", json=PERIOD).status_code == 404
        assert client.get("/api/v1/prices/UNKNOWN/coverage").status_code == 404
        assert app.state.analysis_slots.acquire(blocking=False)
        assert app.state.analysis_slots.acquire(blocking=False)
        try:
            assert client.post("/api/v1/prices/SPY/refresh", json=PERIOD).status_code == 503
        finally:
            app.state.analysis_slots.release()
            app.state.analysis_slots.release()
    assert calls == []


def test_streamed_refresh_body_limit_precedes_provider_io(db: Engine) -> None:
    calls: list[httpx.Request] = []
    with TestClient(create_app(engine=db, provider=mock_provider(calls))) as client:
        response = client.post("/api/v1/prices/SPY/refresh", content=iter([b"x" * 32768] * 3))
        assert response.status_code == 413
    assert calls == []


def test_completed_session_excludes_today_and_respects_holidays() -> None:
    assert completed_session_before_today(datetime(2024, 1, 16, 23, tzinfo=UTC)) == date(
        2024, 1, 12
    )
    # At 01:00 UTC Thursday it is Wednesday in New York: Tuesday is the cutoff.
    assert completed_session_before_today(datetime(2024, 1, 18, 1, tzinfo=UTC)) == date(2024, 1, 16)
    with pytest.raises(ValueError, match="aware"):
        completed_session_before_today(datetime(2024, 1, 16))
