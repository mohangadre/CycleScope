from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from cyclescope.api.app import SCHEMA_REVISION
from cyclescope.domain.errors import InsufficientData, InvalidProviderData
from cyclescope.domain.models import BarBatch, DateRange
from cyclescope.providers.synthetic import SyntheticProvider
from cyclescope.services.ingestion import ingest
from cyclescope.storage.models import DailyBarRow, IngestionRunRow, InstrumentRow

pytestmark = pytest.mark.postgres
PERIOD = DateRange(start=date(2024, 1, 2), end=date(2024, 1, 3))


class RevisedProvider(SyntheticProvider):
    def get_daily_bars(self, symbol: str, start: date, end: date) -> BarBatch:
        batch = super().get_daily_bars(symbol, start, end)
        changed = batch.bars[0].model_copy(update={"close": Decimal("100.5")})
        return batch.model_copy(update={"bars": (changed, *batch.bars[1:])})


def test_idempotent_bars_with_immutable_snapshots_and_revisions(db: Engine) -> None:
    first = ingest(db, SyntheticProvider(), "SPY", PERIOD)
    second = ingest(db, SyntheticProvider(), "SPY", PERIOD)
    revised = ingest(db, RevisedProvider(), "SPY", PERIOD)
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(InstrumentRow)) == 1
        assert session.scalar(select(func.count()).select_from(DailyBarRow)) == 2
        assert session.scalar(select(func.count()).select_from(IngestionRunRow)) == 3
        a, b, c = [session.get(IngestionRunRow, run) for run in (first, second, revised)]
        assert a.content_hash == b.content_hash != c.content_hash
        assert a.payload[0]["close"] == "100.0000"
        assert c.payload[0]["close"] == "100.5"
        assert a.request_start == PERIOD.start and a.request_end == PERIOD.end
        assert a.fetched_at.utcoffset().total_seconds() == 0
        assert a.ingested_at.utcoffset().total_seconds() == 0
        current = session.scalar(select(DailyBarRow).order_by(DailyBarRow.session_date))
        assert current.close == Decimal("100.5")
        assert current.ingestion_run_id == revised


def test_missing_sessions_abort_without_partial_persistence(db: Engine) -> None:
    with pytest.raises(InsufficientData):
        ingest(db, SyntheticProvider(), "SPY", DateRange(start=date(2023, 12, 29), end=PERIOD.end))
    with Session(db) as session:
        for model in (InstrumentRow, IngestionRunRow, DailyBarRow):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_rejects_mismatched_provenance(db: Engine) -> None:
    class BrokenProvider(SyntheticProvider):
        def get_daily_bars(self, symbol: str, start: date, end: date) -> BarBatch:
            batch = super().get_daily_bars(symbol, start, end)
            return batch.model_copy(update={"provider": "untruthful"})

    with pytest.raises(InvalidProviderData, match="provenance"):
        ingest(db, BrokenProvider(), "SPY", PERIOD)


def test_database_constraints_and_transaction_rollback(db: Engine) -> None:
    run = ingest(db, SyntheticProvider(), "SPY", PERIOD)
    with pytest.raises(IntegrityError), db.begin() as connection:
        connection.execute(update(DailyBarRow).values(volume=-1))
    with pytest.raises(IntegrityError), db.begin() as connection:
        connection.execute(update(DailyBarRow).values(low=0))
    with pytest.raises(IntegrityError), db.begin() as connection:
        connection.execute(text("INSERT INTO daily_bars SELECT * FROM daily_bars LIMIT 1"))
    with Session(db) as session:
        assert session.get(IngestionRunRow, run) is not None
        assert session.scalar(select(func.count()).select_from(DailyBarRow)) == 2


def test_migrations_downgrade_upgrade_and_model_parity(db: Engine) -> None:
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    command.check(config)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)
    with db.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == SCHEMA_REVISION


def test_week2_migration_preserves_week1_bars_and_ingestion_snapshots(db: Engine) -> None:
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    command.downgrade(config, "0001")
    run_id = ingest(db, SyntheticProvider(), "SPY", PERIOD)
    command.upgrade(config, "head")
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(DailyBarRow)) == 2
        assert session.get(IngestionRunRow, run_id).payload[0]["symbol"] == "SPY"
