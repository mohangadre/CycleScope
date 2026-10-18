from datetime import datetime
from typing import Literal
from uuid import UUID

from cyclescope.domain.models import (
    AdjustmentBasis,
    DailyBar,
    DataKind,
    DateRange,
    DomainModel,
    Instrument,
    Symbol,
)


class ErrorDetail(DomainModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(DomainModel):
    error: ErrorDetail


class HealthResponse(DomainModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ready", "unavailable"]
    provider: str
    data_kind: DataKind


class SymbolsResponse(DomainModel):
    provider: str
    data_kind: DataKind
    instruments: tuple[Instrument, ...]


class StoredBar(DailyBar):
    ingestion_run_id: UUID
    ingested_at: datetime
    data_version: str
    fetched_at: datetime
    snapshot_hash: str


class PricesResponse(DomainModel):
    ticker: Symbol
    provider: str
    data_kind: DataKind
    adjustment_basis: AdjustmentBasis
    currency: Literal["USD"] = "USD"
    date_basis: Literal["exchange_session"] = "exchange_session"
    calendar: Literal["XNYS"] = "XNYS"
    price_unit: Literal["USD_per_share"] = "USD_per_share"
    volume_unit: Literal["shares"] = "shares"
    requested_range: DateRange
    total: int
    limit: int
    offset: int
    has_more: bool
    warnings: tuple[str, ...]
    bars: tuple[StoredBar, ...]
