from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Symbol = Annotated[
    str, StringConstraints(pattern=r"^[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,4})?$", max_length=15)
]
DataKind = Literal["synthetic", "real"]
AdjustmentBasis = Literal["split_dividend_adjusted"]
Price = Annotated[Decimal, Field(gt=0, allow_inf_nan=False, max_digits=22, decimal_places=8)]


class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DateRange(DomainModel):
    start: date
    end: date

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if self.end < self.start:
            raise ValueError("end must be on or after start")
        if (self.end - self.start).days > 3660:
            raise ValueError("date range must not exceed 3660 calendar days")
        if self.start < date(1990, 1, 1) or self.end > date(2035, 12, 31):
            raise ValueError("supported calendar range is 1990-01-01 through 2035-12-31")
        return self


class Instrument(DomainModel):
    symbol: Symbol
    display_name: str
    asset_class: Literal["equity", "etf"]
    exchange: str
    calendar: Literal["XNYS"] = "XNYS"
    currency: Literal["USD"] = "USD"


CORE_CATALOG = (
    Instrument(symbol="SPY", display_name="SPDR S&P 500 ETF", asset_class="etf", exchange="ARCX"),
    Instrument(symbol="QQQ", display_name="Invesco QQQ Trust", asset_class="etf", exchange="XNAS"),
    Instrument(symbol="NVDA", display_name="NVIDIA", asset_class="equity", exchange="XNAS"),
    Instrument(
        symbol="MU", display_name="Micron Technology", asset_class="equity", exchange="XNAS"
    ),
)


SECTOR_CATALOG = tuple(
    Instrument(symbol=symbol, display_name=name, asset_class="etf", exchange="ARCX")
    for symbol, name in (
        ("XLK", "Technology"),
        ("XLF", "Financials"),
        ("XLE", "Energy"),
        ("XLI", "Industrials"),
        ("XLU", "Utilities"),
        ("XLV", "Health care"),
        ("XLY", "Consumer discretionary"),
        ("XLP", "Consumer staples"),
    )
)
CATALOG = (*CORE_CATALOG, *SECTOR_CATALOG)


class DailyBar(DomainModel):
    symbol: Symbol
    session_date: date
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Annotated[int, Field(ge=0, le=2**63 - 1, strict=True)]

    @model_validator(mode="after")
    def valid_ohlc(self) -> Self:
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("OHLC must satisfy low <= open/close <= high")
        return self


class BarBatch(DomainModel):
    symbol: Symbol
    provider: str
    data_kind: DataKind
    adjustment_basis: AdjustmentBasis = "split_dividend_adjusted"
    currency: Literal["USD"] = "USD"
    data_version: str
    fetched_at: datetime
    bars: tuple[DailyBar, ...]

    @model_validator(mode="after")
    def timezone_required(self) -> Self:
        if self.fetched_at.utcoffset() is None:
            raise ValueError("fetched_at must have a timezone")
        return self
