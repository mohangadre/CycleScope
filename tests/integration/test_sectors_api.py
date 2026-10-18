from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from alembic import command
from cyclescope.api.app import create_app
from cyclescope.domain.calendar import trailing_sessions
from cyclescope.domain.experiments import CycleRequest
from cyclescope.domain.models import SECTOR_CATALOG, DateRange
from cyclescope.providers.alpaca import AlpacaProvider
from cyclescope.providers.synthetic import SyntheticProvider
from cyclescope.services.analysis import run_analysis
from cyclescope.services.ingestion import ingest
from cyclescope.storage.models import AnalysisRunRow, DailyBarRow, SectorRunRow

pytestmark = pytest.mark.postgres
END = date(2022, 11, 8)


@pytest.fixture
def sectors_api(db: Engine) -> Iterator[TestClient]:
    provider = SyntheticProvider(research=True)
    dates = trailing_sessions(END, 150)
    for symbol in ("SPY", *(x.symbol for x in SECTOR_CATALOG)):
        ingest(db, provider, symbol, DateRange(start=dates[0], end=END))
    with TestClient(create_app(engine=db, provider=provider)) as client:
        yield client


def test_sector_api_alignment_units_normalization_metadata_and_exact_replay(
    sectors_api: TestClient, db: Engine
) -> None:
    response = sectors_api.get("/api/v1/sectors/rotation", params={"as_of": str(END)})
    assert response.status_code == 200, response.text
    body = response.json()
    result = body["result"]
    assert body["data_kind"] == "synthetic"
    assert result["benchmark"] == "SPY"
    assert result["observation_kind"] == "observed_relative_performance"
    assert result["input_sample_count_per_symbol"] == 150
    assert result["observed_through"] == str(END)
    assert result["momentum_unit"] == "natural_log_relative_strength_change"
    assert len(result["sectors"]) == 8
    assert {x["ticker"] for x in result["sectors"]} == {x.symbol for x in SECTOR_CATALOG}
    for sector in result["sectors"]:
        assert len(sector["points"]) == 126
        assert sector["points"][0]["normalized_rs"] == pytest.approx(100)
        assert sector["points"][0]["smoothed_normalized_rs"] == pytest.approx(100)
        assert all(point["session_date"] <= str(END) for point in sector["points"])
    route = "/api/v1/sectors/runs/" + body["run_id"]
    assert sectors_api.get(route).json() == body
    # Revised current prices cannot rewrite the retained panel or its replay.
    with db.begin() as connection:
        connection.execute(update(DailyBarRow).values(close=DailyBarRow.close * Decimal("1.001")))
    replay = sectors_api.post(route + "/replay")
    assert replay.status_code == 200, replay.text
    assert replay.json() == body
    with Session(db) as session:
        row = session.get(SectorRunRow, UUID(body["run_id"]))
        assert len(row.input_snapshot["dates"]) == 150
        assert len(row.input_snapshot["closes"]) == 9
        assert row.input_hash == body["input_hash"]
    assert "/api/v1/sectors/rotation" in sectors_api.get("/openapi.json").json()["paths"]


def test_sector_relative_strength_uses_matching_adjusted_prices(
    sectors_api: TestClient, db: Engine
) -> None:
    body = sectors_api.get(
        "/api/v1/sectors/rotation", params={"as_of": str(END), "smoothing_sessions": 1}
    ).json()
    with Session(db) as session:
        prices = {
            bar.symbol: float(bar.close)
            for bar in session.scalars(select(DailyBarRow).where(DailyBarRow.session_date == END))
        }
    for sector in body["result"]["sectors"]:
        assert sector["points"][-1]["relative_strength"] == pytest.approx(
            prices[sector["ticker"]] / prices["SPY"]
        )


@pytest.mark.parametrize("fault", ["gap", "feed", "missing_benchmark"])
def test_missing_or_mixed_feed_is_rejected_without_partial_results(
    sectors_api: TestClient, db: Engine, fault: str
) -> None:
    with db.begin() as connection:
        if fault == "gap":
            connection.execute(
                DailyBarRow.__table__.delete().where(
                    DailyBarRow.symbol == "XLK", DailyBarRow.session_date == END
                )
            )
        elif fault == "feed":
            connection.execute(
                update(DailyBarRow).where(DailyBarRow.symbol == "XLK").values(provider="alpaca-iex")
            )
        else:
            connection.execute(DailyBarRow.__table__.delete().where(DailyBarRow.symbol == "SPY"))
    response = sectors_api.get("/api/v1/sectors/rotation", params={"as_of": str(END)})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_data"
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(SectorRunRow)) == 0


@pytest.mark.parametrize(
    "params",
    [
        {"as_of": "2036-01-01"},
        {"as_of": str(END), "lookback_sessions": 31},
        {"as_of": str(END), "momentum_sessions": 0},
        {"as_of": str(END), "smoothing_sessions": 31},
    ],
)
def test_sector_request_validation(sectors_api: TestClient, params: dict[str, object]) -> None:
    assert sectors_api.get("/api/v1/sectors/rotation", params=params).status_code == 422


def test_future_revisions_do_not_change_sector_cutoff_or_input_hash(
    sectors_api: TestClient, db: Engine
) -> None:
    params = {"as_of": str(END), "lookback_sessions": 100}
    original = sectors_api.get("/api/v1/sectors/rotation", params=params).json()
    provider = SyntheticProvider(research=True)
    later = date(2022, 11, 9)
    # Deliberately insert a later bar only through the normal validated adapter.
    from cyclescope.domain.models import BarBatch

    class Later(SyntheticProvider):
        def get_daily_bars(self, symbol: str, start: date, end: date) -> BarBatch:
            batch = provider.get_daily_bars(symbol, END, END)
            return batch.model_copy(
                update={
                    "bars": tuple(
                        bar.model_copy(
                            update={"session_date": later, "close": bar.close * Decimal("1.001")}
                        )
                        for bar in batch.bars
                    )
                }
            )

    for symbol in ("SPY", *(x.symbol for x in SECTOR_CATALOG)):
        ingest(db, Later(research=True), symbol, DateRange(start=later, end=later))
    changed = sectors_api.get("/api/v1/sectors/rotation", params=params).json()
    assert changed["result"] == original["result"]
    assert changed["input_hash"] == original["input_hash"]


@pytest.mark.parametrize("fault", ["software", "snapshot"])
def test_sector_replay_detects_incompatible_environment_and_tampered_input(
    sectors_api: TestClient, db: Engine, fault: str
) -> None:
    body = sectors_api.get("/api/v1/sectors/rotation", params={"as_of": str(END)}).json()
    with Session(db) as session, session.begin():
        row = session.get(SectorRunRow, UUID(body["run_id"]))
        if fault == "software":
            row.response = {
                **row.response,
                "software": {**row.response["software"], "code_sha256": "changed"},
            }
        else:
            row.input_snapshot = {**row.input_snapshot, "provider": "changed"}
    assert sectors_api.post("/api/v1/sectors/runs/" + body["run_id"] + "/replay").status_code == 409


def test_real_provider_never_reads_synthetic_sector_rows_and_unknown_id_is_404(
    db: Engine, sectors_api: TestClient
) -> None:
    with TestClient(create_app(engine=db, provider=AlpacaProvider(None, None))) as client:
        assert client.get("/api/v1/sectors/rotation", params={"as_of": str(END)}).status_code == 422
    assert sectors_api.get("/api/v1/sectors/runs/" + str(uuid4())).status_code == 404


def test_sector_migration_preserves_prior_price_and_analysis_records(
    db: Engine, sectors_api: TestClient
) -> None:
    provider = SyntheticProvider(research=True)
    analysis = run_analysis(db, provider, "SPY", CycleRequest(as_of=END, lookback=40))
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    command.downgrade(config, "0002")
    command.upgrade(config, "head")
    command.check(config)
    with Session(db) as session:
        assert session.get(AnalysisRunRow, analysis.run_id) is not None
        assert session.scalar(select(func.count()).select_from(DailyBarRow)) == 1350
