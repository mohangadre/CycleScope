from datetime import UTC, datetime

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, load_only

from cyclescope.domain.calendar import session_dates
from cyclescope.domain.errors import InsufficientData
from cyclescope.domain.models import DateRange
from cyclescope.domain.views import PricesResponse, StoredBar
from cyclescope.providers.base import MarketDataProvider, instrument_for
from cyclescope.storage.models import DailyBarRow, IngestionRunRow


def read_prices(
    engine: Engine,
    provider: MarketDataProvider,
    symbol: str,
    period: DateRange,
    limit: int,
    offset: int,
) -> PricesResponse:
    instrument_for(symbol)
    criteria = (
        DailyBarRow.symbol == symbol,
        DailyBarRow.provider == provider.provider_id,
        DailyBarRow.data_kind == provider.data_kind,
        DailyBarRow.adjustment_basis == "split_dividend_adjusted",
        DailyBarRow.session_date.between(period.start, period.end),
    )
    # Count, page, and coverage must describe one snapshot during concurrent ingestion.
    snapshot_engine = engine.execution_options(isolation_level="REPEATABLE READ")
    with Session(snapshot_engine) as session, session.begin():
        total = session.scalar(select(func.count()).select_from(DailyBarRow).where(*criteria)) or 0
        if not total:
            raise InsufficientData(
                "No stored bars in this range for the selected provider; ingest first"
            )
        rows = session.execute(
            select(DailyBarRow, IngestionRunRow)
            # Never repeat the full retained JSON payload for every price row.
            .options(
                load_only(
                    IngestionRunRow.data_version,
                    IngestionRunRow.fetched_at,
                    IngestionRunRow.content_hash,
                )
            )
            .join(IngestionRunRow, DailyBarRow.ingestion_run_id == IngestionRunRow.id)
            .where(*criteria)
            .order_by(DailyBarRow.session_date)
            .offset(offset)
            .limit(limit)
        ).all()
        dates = set(session.scalars(select(DailyBarRow.session_date).where(*criteria)))
        bars = tuple(
            StoredBar(
                symbol=bar.symbol,
                session_date=bar.session_date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                ingestion_run_id=bar.ingestion_run_id,
                ingested_at=bar.ingested_at,
                data_version=run.data_version,
                fetched_at=run.fetched_at,
                snapshot_hash=run.content_hash,
            )
            for bar, run in rows
        )
    warnings = []
    if set(session_dates(period)) - dates:
        warnings.append("stored_coverage_incomplete_for_requested_range")
    if max(dates) < datetime.now(UTC).date():
        warnings.append("historical_data_only_not_a_live_quote")
    return PricesResponse(
        ticker=symbol,
        provider=provider.provider_id,
        data_kind=provider.data_kind,
        adjustment_basis="split_dividend_adjusted",
        requested_range=period,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(bars) < total,
        warnings=tuple(warnings),
        bars=bars,
    )
