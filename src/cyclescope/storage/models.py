from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy import Uuid as SqlUuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class InstrumentRow(Base):
    __tablename__ = "instruments"
    symbol: Mapped[str] = mapped_column(String(15), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    asset_class: Mapped[str] = mapped_column(String(16))
    exchange: Mapped[str] = mapped_column(String(16))
    calendar: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3))


class IngestionRunRow(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[UUID] = mapped_column(SqlUuid, primary_key=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"))
    provider: Mapped[str] = mapped_column(String(32))
    adjustment_basis: Mapped[str] = mapped_column(String(32))
    data_kind: Mapped[str] = mapped_column(String(16))
    data_version: Mapped[str] = mapped_column(String(120))
    request_start: Mapped[date]
    request_end: Mapped[date]
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64))
    bar_count: Mapped[int]
    # Immutable normalized input snapshot, retained even when the latest bars are updated.
    payload: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    __table_args__ = (
        CheckConstraint("bar_count > 0", name="ck_run_nonempty"),
        CheckConstraint("request_end >= request_start", name="ck_run_range"),
        CheckConstraint("data_kind IN ('synthetic', 'real')", name="ck_run_data_kind"),
    )


class DailyBarRow(Base):
    __tablename__ = "daily_bars"
    symbol: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"), primary_key=True)
    session_date: Mapped[date] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    adjustment_basis: Mapped[str] = mapped_column(String(32), primary_key=True)
    data_kind: Mapped[str] = mapped_column(String(16))
    open: Mapped[Decimal] = mapped_column(Numeric(22, 8))
    high: Mapped[Decimal] = mapped_column(Numeric(22, 8))
    low: Mapped[Decimal] = mapped_column(Numeric(22, 8))
    close: Mapped[Decimal] = mapped_column(Numeric(22, 8))
    volume: Mapped[int] = mapped_column(BigInteger)
    ingestion_run_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_runs.id"))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "low > 0 AND low <= open AND low <= close AND high >= open AND high >= close",
            name="ck_bar_ohlc",
        ),
        CheckConstraint("volume >= 0", name="ck_bar_volume"),
        CheckConstraint("data_kind IN ('synthetic', 'real')", name="ck_bar_data_kind"),
        CheckConstraint("adjustment_basis = 'split_dividend_adjusted'", name="ck_bar_adjustment"),
        Index("ix_bars_symbol_session", "symbol", "session_date"),
    )


class AnalysisRunRow(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[UUID] = mapped_column(SqlUuid, primary_key=True)
    ticker: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"))
    kind: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_hash: Mapped[str] = mapped_column(String(64))
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    request_config: Mapped[dict[str, Any]] = mapped_column(JSON)
    response: Mapped[dict[str, Any]] = mapped_column(JSON)
    __table_args__ = (
        CheckConstraint("kind IN ('cycles', 'forecast', 'backtest')", name="ck_analysis_kind"),
        Index("ix_analysis_ticker_created", "ticker", "created_at"),
    )


class SectorRunRow(Base):
    __tablename__ = "sector_runs"
    id: Mapped[UUID] = mapped_column(SqlUuid, primary_key=True)
    benchmark: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"))
    provider: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_hash: Mapped[str] = mapped_column(String(64))
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    request_config: Mapped[dict[str, Any]] = mapped_column(JSON)
    response: Mapped[dict[str, Any]] = mapped_column(JSON)
    __table_args__ = (Index("ix_sector_provider_created", "provider", "created_at"),)
