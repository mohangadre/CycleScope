"""Read a bounded, consistent input snapshot without loading future ingestion payloads."""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from cyclescope.analytics.series import MAX_SAMPLES, PriceSeries
from cyclescope.domain.calendar import session_dates
from cyclescope.domain.errors import AnalysisNotFound, InsufficientData
from cyclescope.domain.experiments import AnalysisResponse, InputSnapshot
from cyclescope.domain.models import DateRange
from cyclescope.providers.base import MarketDataProvider, instrument_for
from cyclescope.storage.models import AnalysisRunRow, DailyBarRow, IngestionRunRow


def load_snapshot(
    engine: Engine,
    provider: MarketDataProvider,
    ticker: str,
    *,
    end: date,
    start: date | None = None,
    lookback: int | None = None,
) -> InputSnapshot:
    instrument_for(ticker)
    criteria = [
        DailyBarRow.symbol == ticker,
        DailyBarRow.provider == provider.provider_id,
        DailyBarRow.data_kind == provider.data_kind,
        DailyBarRow.adjustment_basis == "split_dividend_adjusted",
        DailyBarRow.session_date <= end,
    ]
    if start is not None:
        DateRange(start=start, end=end)
        criteria.append(DailyBarRow.session_date >= start)
    else:
        DateRange(start=end, end=end)
    query = (
        select(
            DailyBarRow.session_date,
            DailyBarRow.close,
            DailyBarRow.ingestion_run_id,
            IngestionRunRow.data_version,
        )
        .join(IngestionRunRow, DailyBarRow.ingestion_run_id == IngestionRunRow.id)
        .where(*criteria)
        .order_by(DailyBarRow.session_date.desc())
        .limit(lookback or MAX_SAMPLES + 1)
    )
    with Session(engine.execution_options(isolation_level="REPEATABLE READ")) as session:
        rows = list(reversed(session.execute(query).all()))
    if not rows:
        raise InsufficientData(
            "No stored data for this provider/range; ingest explicitly before analysis"
        )
    snapshot = InputSnapshot(
        ticker=ticker,
        provider=provider.provider_id,
        data_kind=provider.data_kind,
        data_versions=tuple(sorted({row.data_version for row in rows})),
        ingestion_run_ids=tuple(sorted({row.ingestion_run_id for row in rows}, key=str)),
        dates=tuple(row.session_date for row in rows),
        closes=tuple(row.close for row in rows),
    )
    series = PriceSeries(snapshot.dates, tuple(float(value) for value in snapshot.closes))
    if lookback is not None:
        series.through(end, lookback)
    else:
        series.validate()
        if start is not None and snapshot.dates != session_dates(DateRange(start=start, end=end)):
            raise InsufficientData(
                "Stored data does not completely cover the requested evaluation interval"
            )
    return snapshot


def store_run(
    engine: Engine, response: AnalysisResponse, snapshot: InputSnapshot, config: dict[str, object]
) -> None:
    with Session(engine) as session, session.begin():
        session.add(
            AnalysisRunRow(
                id=response.run_id,
                ticker=snapshot.ticker,
                kind=response.kind,
                created_at=response.created_at,
                input_hash=snapshot.content_hash(),
                input_snapshot=snapshot.model_dump(mode="json"),
                request_config=config,
                response=response.model_dump(mode="json"),
            )
        )


def load_run(
    engine: Engine, run_id: UUID
) -> tuple[AnalysisResponse, InputSnapshot, dict[str, object]]:
    response, snapshot, config = load_raw_run(engine, run_id)
    return AnalysisResponse.model_validate(response), InputSnapshot.model_validate(snapshot), config


def load_raw_run(
    engine: Engine, run_id: UUID
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Retrieve immutable JSON without applying today's model/configuration defaults."""
    with Session(engine) as session:
        row = session.get(AnalysisRunRow, run_id)
        if row is None:
            raise AnalysisNotFound("No saved analysis exists with this run ID")
        return (
            row.response,
            row.input_snapshot,
            row.request_config,
        )
