import json
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from cyclescope.api.app import create_app
from cyclescope.domain.models import BarBatch, DateRange
from cyclescope.providers.alpaca import AlpacaProvider
from cyclescope.providers.synthetic import SyntheticProvider
from cyclescope.services.ingestion import ingest
from cyclescope.storage.models import AnalysisRunRow, DailyBarRow

pytestmark = pytest.mark.postgres


@pytest.fixture
def research(db: Engine) -> tuple[SyntheticProvider, BarBatch]:
    provider = SyntheticProvider(research=True)
    batch = provider.get_daily_bars("SPY", date(2020, 1, 2), date(2024, 12, 31))
    ingest(
        db,
        provider,
        "SPY",
        DateRange(start=batch.bars[0].session_date, end=batch.bars[-1].session_date),
    )
    return provider, batch


@pytest.fixture
def api(db: Engine, research: tuple[SyntheticProvider, BarBatch]) -> Iterator[TestClient]:
    with TestClient(create_app(engine=db, provider=research[0])) as client:
        yield client


def backtest_request(batch: BarBatch) -> dict[str, object]:
    return {
        "ticker": "SPY",
        "start": str(batch.bars[0].session_date),
        "end": str(batch.bars[-1].session_date),
        "evaluation": {
            "initial_train_sessions": 360,
            "horizon_sessions": 20,
            "model": {"bootstrap_draws": 50, "seed": 17},
        },
    }


def test_cycles_cutoff_units_provenance_persistence_and_openapi(
    api: TestClient, research: tuple[SyntheticProvider, BarBatch], db: Engine
) -> None:
    cutoff = str(research[1].bars[479].session_date)
    response = api.get("/api/v1/cycles/SPY", params={"as_of": cutoff, "lookback": 480})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "cycles"
    assert body["source"]["data_kind"] == "synthetic"
    assert body["source"]["provider"] == "synthetic-research-v1"
    assert body["source"]["sample_count"] == 480
    assert len(body["source"]["input_hash"]) == 64
    result = body["result"]
    assert result["forecast_origin"] == result["as_of"] == cutoff
    assert result["analysis"]["period_unit"] == "trading_sessions"
    assert {round(cycle["period_sessions"]) for cycle in result["analysis"]["cycles"]} >= {40, 120}
    assert all(
        cycle["significance_status"] == "not_tested" for cycle in result["analysis"]["cycles"]
    )
    assert api.get("/api/v1/analyses/" + body["run_id"]).json() == body
    with Session(db) as session:
        row = session.get(AnalysisRunRow, UUID(body["run_id"]))
        assert len(row.input_snapshot["dates"]) == 480
        assert row.input_snapshot["dates"][-1] == cutoff
        assert row.input_hash == body["source"]["input_hash"]
    spec = api.get("/openapi.json").json()
    assert "/api/v1/cycles/{ticker}" in spec["paths"]
    assert "/api/v1/forecasts/{ticker}" in spec["paths"]
    assert "/api/v1/backtests" in spec["paths"]


def test_forecast_endpoint_has_strictly_future_dates_and_uncertainty_caveats(
    api: TestClient, research: tuple[SyntheticProvider, BarBatch]
) -> None:
    cutoff = str(research[1].bars[479].session_date)
    response = api.post(
        "/api/v1/forecasts/SPY", json={"as_of": cutoff, "lookback": 480, "horizon_sessions": 60}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    forecast = body["result"]
    assert body["schema_version"] == "analysis-v2"
    assert forecast["fit"]["model_version"] == "harmonic-increment-log-price-v2"
    assert forecast["fit"]["projection_method"] == "conditional_fitted_change"
    assert forecast["fit"]["frequency_refinement"] is not None
    assert forecast["training_sample_count"] == 480
    assert forecast["horizon_sessions"] == len(forecast["points"]) == 60
    assert all(point["session_date"] > cutoff for point in forecast["points"])
    assert all(0 < point["lower"] <= point["upper"] for point in forecast["points"])
    assert forecast["uncertainty"]["calibrated"] is False
    assert forecast["turning_points"]
    assert all(event["window_start"] > cutoff for event in forecast["turning_points"])
    assert api.get("/api/v1/analyses/" + body["run_id"]).json() == body
    assert api.get("/api/v1/backtests/" + body["run_id"]).status_code == 404


def test_backtest_report_roundtrip_and_replay_ignores_revised_live_storage(
    api: TestClient, research: tuple[SyntheticProvider, BarBatch], db: Engine
) -> None:
    response = api.post("/api/v1/backtests", json=backtest_request(research[1]))
    assert response.status_code == 200, response.text
    body = response.json()
    report = body["result"]
    assert report["fold_count"] == 18
    assert (
        report["harmonic_metrics"]["error_count"]
        == report["baseline_metrics"]["error_count"]
        == 360
    )
    assert report["harmonic_metrics"]["direction_count"] == 18
    assert all(fold["train_end"] < fold["test_start"] for fold in report["folds"])
    assert body["software"]["libraries"]["scipy"]
    original = api.get("/api/v1/backtests/" + body["run_id"])
    assert original.json() == body
    with db.begin() as connection:
        connection.execute(update(DailyBarRow).values(close=DailyBarRow.close * Decimal("1.001")))
    replayed = api.post("/api/v1/backtests/" + body["run_id"] + "/replay")
    assert replayed.status_code == 200, replayed.text
    assert replayed.json() == body
    assert api.get("/api/v1/backtests/" + body["run_id"]).json() == body
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(AnalysisRunRow)) == 1


def test_future_reingestion_cannot_change_cutoff_model_or_numerical_input_hash(
    api: TestClient, research: tuple[SyntheticProvider, BarBatch], db: Engine
) -> None:
    cutoff = research[1].bars[479].session_date
    request = {"as_of": str(cutoff), "lookback": 480, "horizon_sessions": 20}
    original = api.post("/api/v1/forecasts/SPY", json=request).json()

    class FutureRevision(SyntheticProvider):
        def get_daily_bars(self, symbol: str, start: date, end: date) -> BarBatch:
            batch = super().get_daily_bars(symbol, start, end)
            bars = tuple(
                bar
                if bar.session_date <= cutoff
                else bar.model_copy(update={"close": bar.close * Decimal("1.001")})
                for bar in batch.bars
            )
            return batch.model_copy(update={"bars": bars})

    batch = research[1]
    ingest(
        db,
        FutureRevision(research=True),
        "SPY",
        DateRange(start=batch.bars[0].session_date, end=batch.bars[-1].session_date),
    )
    changed = api.post("/api/v1/forecasts/SPY", json=request).json()
    assert original["result"] == changed["result"]
    assert original["source"]["input_hash"] == changed["source"]["input_hash"]
    assert original["source"]["ingestion_run_ids"] != changed["source"]["ingestion_run_ids"]


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/v1/forecasts/SPY", {"as_of": "2022-01-03", "horizon_sessions": 0}),
        ("/api/v1/forecasts/SPY", {"as_of": "2022-01-03", "horizon_sessions": 127}),
        ("/api/v1/forecasts/SPY", {"as_of": "2036-01-03"}),
        ("/api/v1/forecasts/SPY", {"as_of": "2022-01-03", "model": {"max_harmonics": 4}}),
        ("/api/v1/backtests", {"ticker": "SPY", "start": "2022-02-01", "end": "2022-01-01"}),
        ("/api/v1/backtests", {"ticker": "spy", "start": "2022-01-01", "end": "2022-02-01"}),
        (
            "/api/v1/backtests",
            {
                "ticker": "SPY",
                "start": "2022-01-01",
                "end": "2022-02-01",
                "evaluation": {"step_sessions": 1},
            },
        ),
    ],
)
def test_request_validation_before_computation(
    api: TestClient, path: str, payload: dict[str, object]
) -> None:
    response = api.post(path, json=payload)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize(
    "ticker,params,status",
    [
        ("ZZZZ", {"as_of": "2022-01-03"}, 404),
        ("SPY", {"as_of": "2022-01-03", "lookback": 10}, 422),
        (
            "SPY",
            {"as_of": "2022-01-03", "min_period_sessions": 120, "max_period_sessions": 40},
            422,
        ),
        ("SPY", {"as_of": "2025-01-03", "lookback": 480}, 422),
    ],
)
def test_cycle_errors(api: TestClient, ticker: str, params: dict[str, object], status: int) -> None:
    response = api.get("/api/v1/cycles/" + ticker, params=params)
    assert response.status_code == status, response.text


def test_missing_ids_and_real_mode_do_not_fall_back(api: TestClient, db: Engine) -> None:
    assert api.get("/api/v1/backtests/" + str(uuid4())).status_code == 404
    assert api.get("/api/v1/backtests/not-a-uuid").status_code == 422
    with TestClient(create_app(engine=db, provider=AlpacaProvider(None, None))) as client:
        response = client.get("/api/v1/cycles/SPY", params={"as_of": "2022-01-03", "lookback": 480})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "insufficient_data"


def test_analysis_capacity_is_bounded(db: Engine) -> None:
    app = create_app(engine=db)
    assert app.state.analysis_slots.acquire(blocking=False)
    assert app.state.analysis_slots.acquire(blocking=False)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/cycles/SPY", params={"as_of": "2022-01-03"})
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "analysis_busy"
    finally:
        app.state.analysis_slots.release()
        app.state.analysis_slots.release()


def test_replay_detects_changed_software_identity(
    api: TestClient, research: tuple[SyntheticProvider, BarBatch], db: Engine
) -> None:
    saved = api.post("/api/v1/backtests", json=backtest_request(research[1])).json()
    with Session(db) as session, session.begin():
        row = session.get(AnalysisRunRow, UUID(saved["run_id"]))
        changed = {
            **row.response,
            "software": {**row.response["software"], "code_sha256": "changed"},
        }
        row.response = changed
    response = api.post("/api/v1/backtests/" + saved["run_id"] + "/replay")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "replay_environment_mismatch"


def test_legacy_report_remains_exact_and_cannot_replay_with_new_defaults(
    api: TestClient, db: Engine
) -> None:
    path = Path(__file__).parents[2] / "docs/experiments/legacy/synthetic-week2-v1.json"
    original = json.loads(path.read_text())
    with Session(db) as session, session.begin():
        session.add(
            AnalysisRunRow(
                id=UUID(original["run_id"]),
                ticker="SPY",
                kind="backtest",
                created_at=datetime.fromisoformat(original["created_at"]),
                input_hash=original["source"]["input_hash"],
                # Deliberately cannot be parsed: version rejection must come first.
                input_snapshot={},
                request_config={},
                response=original,
            )
        )
    for route in ("backtests", "analyses"):
        saved = api.get(f"/api/v1/{route}/{original['run_id']}")
        assert saved.status_code == 200
        assert saved.json() == original
        assert "refine_frequencies" not in saved.json()["result"]["config"]["model"]
    replayed = api.post(f"/api/v1/backtests/{original['run_id']}/replay")
    assert replayed.status_code == 409
    assert replayed.json()["error"]["code"] == "replay_environment_mismatch"
