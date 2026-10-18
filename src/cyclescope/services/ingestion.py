import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from cyclescope.domain.calendar import session_dates
from cyclescope.domain.errors import InsufficientData, InvalidProviderData
from cyclescope.domain.models import BarBatch, DateRange
from cyclescope.providers.base import MarketDataProvider, instrument_for
from cyclescope.storage.models import DailyBarRow, IngestionRunRow, InstrumentRow


def validate_batch(batch: BarBatch, symbol: str, period: DateRange) -> None:
    expected = session_dates(period)
    if not expected or not batch.bars:
        raise InsufficientData("No trading-session bars available in requested range")
    if batch.symbol != symbol or any(bar.symbol != symbol for bar in batch.bars):
        raise InvalidProviderData("Provider returned a mismatched symbol")
    observed = tuple(bar.session_date for bar in batch.bars)
    if observed != tuple(sorted(set(observed))):
        raise InvalidProviderData("Provider bars must be unique and ordered by session date")
    if set(observed) - set(expected):
        raise InvalidProviderData("Provider returned out-of-range or non-session dates")
    if set(expected) - set(observed):
        raise InsufficientData("Missing trading sessions in requested range; ingestion aborted")


def ingest(engine: Engine, provider: MarketDataProvider, symbol: str, period: DateRange) -> UUID:
    instrument = instrument_for(symbol)
    batch = provider.get_daily_bars(symbol, period.start, period.end)
    validate_batch(batch, symbol, period)
    if batch.provider != provider.provider_id or batch.data_kind != provider.data_kind:
        raise InvalidProviderData("Batch provenance does not match selected provider")
    payload = [bar.model_dump(mode="json") for bar in batch.bars]
    canonical = json.dumps(
        {
            "provider": batch.provider,
            "data_kind": batch.data_kind,
            "data_version": batch.data_version,
            "currency": batch.currency,
            "basis": batch.adjustment_basis,
            "bars": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    run_id = uuid4()
    now = datetime.now(UTC)
    # Network and validation finish before the transaction; failures cannot partially ingest.
    with Session(engine) as session, session.begin():
        statement = insert(InstrumentRow).values(**instrument.model_dump())
        session.execute(statement.on_conflict_do_nothing(index_elements=["symbol"]))
        session.add(
            IngestionRunRow(
                id=run_id,
                symbol=symbol,
                provider=batch.provider,
                adjustment_basis=batch.adjustment_basis,
                data_kind=batch.data_kind,
                data_version=batch.data_version,
                request_start=period.start,
                request_end=period.end,
                fetched_at=batch.fetched_at,
                ingested_at=now,
                content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
                bar_count=len(batch.bars),
                payload=payload,
            )
        )
        session.flush()
        values = [
            {
                **bar.model_dump(),
                "provider": batch.provider,
                "adjustment_basis": batch.adjustment_basis,
                "data_kind": batch.data_kind,
                "ingestion_run_id": run_id,
                "ingested_at": now,
            }
            for bar in batch.bars
        ]
        upsert = insert(DailyBarRow).values(values)
        keys = ["symbol", "session_date", "provider", "adjustment_basis"]
        session.execute(
            upsert.on_conflict_do_update(
                index_elements=keys,
                set_={key: getattr(upsert.excluded, key) for key in values[0] if key not in keys},
            )
        )
    return run_id
