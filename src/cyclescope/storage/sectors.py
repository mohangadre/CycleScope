"""Load one repeatable-read panel, with strict feed/basis/session alignment."""

from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from cyclescope.domain.calendar import trailing_sessions
from cyclescope.domain.errors import AnalysisNotFound, InsufficientData
from cyclescope.domain.models import SECTOR_CATALOG
from cyclescope.domain.sectors import SectorInput, SectorRequest, SectorResponse
from cyclescope.providers.base import MarketDataProvider
from cyclescope.storage.models import DailyBarRow, IngestionRunRow, SectorRunRow


def load_sector_input(
    engine: Engine, provider: MarketDataProvider, config: SectorRequest
) -> SectorInput:
    dates = trailing_sessions(config.as_of, config.required_sessions)
    symbols = ("SPY", *(item.symbol for item in SECTOR_CATALOG))
    query = (
        select(DailyBarRow, IngestionRunRow.data_version)
        .join(IngestionRunRow, DailyBarRow.ingestion_run_id == IngestionRunRow.id)
        .where(
            DailyBarRow.symbol.in_(symbols),
            DailyBarRow.provider == provider.provider_id,
            DailyBarRow.data_kind == provider.data_kind,
            DailyBarRow.adjustment_basis == "split_dividend_adjusted",
            DailyBarRow.session_date.between(dates[0], dates[-1]),
        )
        .order_by(DailyBarRow.symbol, DailyBarRow.session_date)
    )
    with (
        Session(engine.execution_options(isolation_level="REPEATABLE READ")) as session,
        session.begin(),
    ):
        rows = session.execute(query).all()
        closes = {}
        versions = {}
        runs = {}
        for symbol in symbols:
            selected = [(bar, version) for bar, version in rows if bar.symbol == symbol]
            if tuple(bar.session_date for bar, _ in selected) != dates:
                raise InsufficientData(
                    f"{symbol} lacks matching sector history ({dates[0]}–{dates[-1]}); "
                    "ingest the configured feed explicitly"
                )
            closes[symbol] = tuple(bar.close for bar, _ in selected)
            versions[symbol] = tuple(sorted({version for _, version in selected}))
            runs[symbol] = tuple(sorted({bar.ingestion_run_id for bar, _ in selected}, key=str))
        return SectorInput(
            provider=provider.provider_id,
            data_kind=provider.data_kind,
            dates=dates,
            closes=closes,
            data_versions=versions,
            ingestion_run_ids=runs,
        )


def store_sector_run(engine: Engine, response: SectorResponse, snapshot: SectorInput) -> None:
    with Session(engine) as session, session.begin():
        session.add(
            SectorRunRow(
                id=response.run_id,
                benchmark="SPY",
                provider=response.provider,
                created_at=response.created_at,
                input_hash=response.input_hash,
                input_snapshot=snapshot.model_dump(mode="json"),
                request_config=response.result.config.model_dump(mode="json"),
                response=response.model_dump(mode="json"),
            )
        )


def load_sector_run(engine: Engine, run_id: UUID) -> tuple[dict[str, Any], dict[str, Any]]:
    with Session(engine) as session:
        row = session.get(SectorRunRow, run_id)
        if row is None:
            raise AnalysisNotFound("No saved sector analysis exists with this run ID")
        return row.response, row.input_snapshot
