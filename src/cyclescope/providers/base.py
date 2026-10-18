from datetime import date
from typing import Protocol

from cyclescope.domain.errors import UnknownSymbol
from cyclescope.domain.models import CATALOG, CORE_CATALOG, BarBatch, DataKind, Instrument


class MarketDataProvider(Protocol):
    provider_id: str
    data_kind: DataKind

    def get_daily_bars(self, symbol: str, start: date, end: date) -> BarBatch: ...


def instrument_for(symbol: str) -> Instrument:
    for instrument in CATALOG:
        if instrument.symbol == symbol:
            return instrument
    raise UnknownSymbol("Symbol is not in the supported universe")


def instruments_for(provider: MarketDataProvider) -> tuple[Instrument, ...]:
    return CORE_CATALOG if provider.provider_id == "synthetic-v1" else CATALOG
