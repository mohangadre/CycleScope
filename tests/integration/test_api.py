import logging
from collections.abc import Iterator
from datetime import date
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from cyclescope.api.app import SCHEMA_REVISION, create_app
from cyclescope.config import Settings
from cyclescope.domain.models import CORE_CATALOG as CATALOG
from cyclescope.domain.models import DateRange
from cyclescope.providers.alpaca import AlpacaProvider
from cyclescope.providers.synthetic import SyntheticProvider
from cyclescope.services.ingestion import ingest

pytestmark = pytest.mark.postgres
PERIOD = DateRange(start=date(2024, 1, 2), end=date(2024, 3, 28))
PARAMS = {"start": "2024-01-02", "end": "2024-03-28"}


@pytest.fixture
def client(db: Engine) -> Iterator[TestClient]:
    for instrument in CATALOG:
        ingest(db, SyntheticProvider(), instrument.symbol, PERIOD)
    with TestClient(create_app(engine=db, provider=SyntheticProvider())) as client:
        yield client


def test_fixture_to_postgres_to_api_all_symbols(client: TestClient) -> None:
    assert client.get("/health").json() == {
        "status": "ok",
        "database": "ready",
        "provider": "synthetic-v1",
        "data_kind": "synthetic",
    }
    symbols = client.get("/api/v1/symbols").json()
    assert {item["symbol"] for item in symbols["instruments"]} == {"SPY", "QQQ", "NVDA", "MU"}
    assert symbols["data_kind"] == "synthetic"
    for ticker in ("SPY", "QQQ", "NVDA", "MU"):
        response = client.get(f"/api/v1/prices/{ticker}", params=PARAMS)
        assert response.status_code == 200, response.text
        UUID(response.headers["x-request-id"])
        body = response.json()
        assert body["data_kind"] == "synthetic"
        assert body["adjustment_basis"] == "split_dividend_adjusted"
        assert body["date_basis"] == "exchange_session"
        assert body["price_unit"] == "USD_per_share"
        assert body["volume_unit"] == "shares"
        assert body["total"] == len(body["bars"]) == 61
        assert body["bars"][0]["session_date"] == "2024-01-02"
        assert body["bars"][-1]["session_date"] == "2024-03-28"
        assert body["bars"][0]["ingested_at"].endswith("Z")
        assert len(body["bars"][0]["snapshot_hash"]) == 64
        assert body["has_more"] is False
        assert "historical_data_only_not_a_live_quote" in body["warnings"]
        assert "stored_coverage_incomplete_for_requested_range" not in body["warnings"]
        dates = [bar["session_date"] for bar in body["bars"]]
        assert dates == sorted(set(dates))
        assert "2024-01-15" not in dates


def test_pagination_and_inclusive_range(client: TestClient) -> None:
    pages = [
        client.get("/api/v1/prices/SPY", params={**PARAMS, "limit": 30, "offset": n}).json()
        for n in (0, 30, 60, 90)
    ]
    assert [len(page["bars"]) for page in pages] == [30, 30, 1, 0]
    assert [page["has_more"] for page in pages] == [True, True, False, False]
    dates = [bar["session_date"] for page in pages for bar in page["bars"]]
    assert len(dates) == len(set(dates)) == 61
    response = client.get("/api/v1/prices/SPY", params={"start": "2024-01-03", "end": "2024-01-03"})
    assert response.status_code == 200
    assert response.json()["total"] == 1


@pytest.mark.parametrize(
    "path,params,status,code",
    [
        ("/api/v1/prices/ZZZZ", PARAMS, 404, "unknown_symbol"),
        ("/api/v1/prices/spy", PARAMS, 422, "invalid_request"),
        ("/api/v1/prices/SPY", {}, 422, "invalid_request"),
        ("/api/v1/prices/SPY", {**PARAMS, "limit": 0}, 422, "invalid_request"),
        ("/api/v1/prices/SPY", {**PARAMS, "limit": 1001}, 422, "invalid_request"),
        ("/api/v1/prices/SPY", {**PARAMS, "offset": -1}, 422, "invalid_request"),
        ("/api/v1/prices/SPY", {**PARAMS, "start": "bad-date"}, 422, "invalid_request"),
        ("/api/v1/prices/SPY", {**PARAMS, "end": "2020-01-01"}, 422, "http_error"),
        ("/api/v1/prices/SPY", {**PARAMS, "start": "2000-01-01"}, 422, "http_error"),
        (
            "/api/v1/prices/SPY",
            {"start": "2024-01-15", "end": "2024-01-15"},
            422,
            "insufficient_data",
        ),
        ("/missing", {}, 404, "http_error"),
    ],
)
def test_error_contract(
    client: TestClient, path: str, params: dict[str, object], status: int, code: str
) -> None:
    response = client.get(path, params=params)
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_partial_coverage_is_explicit(client: TestClient) -> None:
    response = client.get("/api/v1/prices/SPY", params={**PARAMS, "end": "2024-04-01"})
    assert response.status_code == 200
    assert "stored_coverage_incomplete_for_requested_range" in response.json()["warnings"]


def test_empty_database_and_real_mode_do_not_substitute_fixtures(db: Engine) -> None:
    with TestClient(create_app(engine=db, provider=SyntheticProvider())) as client:
        assert client.get("/api/v1/prices/SPY", params=PARAMS).status_code == 422
    ingest(db, SyntheticProvider(), "SPY", PERIOD)
    with TestClient(create_app(engine=db, provider=AlpacaProvider(None, None))) as client:
        response = client.get("/api/v1/prices/SPY", params=PARAMS)
        assert response.status_code == 422
        assert client.get("/api/v1/symbols").json()["data_kind"] == "real"


def test_readiness_detects_schema_mismatch_but_liveness_survives(db: Engine) -> None:
    with db.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'outdated'"))
    try:
        with TestClient(create_app(engine=db)) as client:
            assert client.get("/health").status_code == 503
            assert client.get("/health/live").status_code == 200
    finally:
        with db.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": SCHEMA_REVISION},
            )


def test_database_outage_is_sanitized_and_docs_work() -> None:
    settings = Settings(database_url="postgresql+psycopg://private:secret@127.0.0.1:1/missing")
    with TestClient(create_app(settings=settings)) as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/health")
        assert response.status_code == 503
        assert "secret" not in response.text
        response = client.get("/api/v1/prices/SPY", params=PARAMS)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "database_unavailable"
        assert "secret" not in response.text
        assert client.get("/docs").status_code == 200
        spec = client.get("/openapi.json").json()
        assert "/api/v1/prices/{ticker}" in spec["paths"]
        assert "PricesResponse" in spec["components"]["schemas"]


def test_unexpected_error_is_sanitized_and_correlated(db: Engine) -> None:
    app = create_app(engine=db)

    @app.get("/failure")
    def failure() -> None:
        raise RuntimeError("sensitive internal information")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/failure")
        assert response.status_code == 500
        assert "sensitive" not in response.text
        assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_logs_have_request_ids_without_query_values(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="cyclescope.requests"):
        response = client.get("/api/v1/symbols?key=must-not-be-logged")
    assert response.headers["x-request-id"] in caplog.text
    assert "must-not-be-logged" not in caplog.text
