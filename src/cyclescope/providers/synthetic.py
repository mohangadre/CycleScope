import csv
import io
import json
from datetime import UTC, date, datetime
from importlib.resources import files

from cyclescope.domain.errors import InsufficientData
from cyclescope.domain.models import CORE_CATALOG, BarBatch, DailyBar, DataKind, DateRange
from cyclescope.providers.base import instrument_for


class SyntheticProvider:
    provider_id = "synthetic-v1"
    data_kind: DataKind = "synthetic"

    def __init__(self, *, research: bool = False) -> None:
        self.research = research
        if research:
            self.provider_id = "synthetic-research-v1"

    def get_daily_bars(self, symbol: str, start: date, end: date) -> BarBatch:
        period = DateRange(start=start, end=end)
        instrument_for(symbol)
        if self.research:
            core = symbol in {item.symbol for item in CORE_CATALOG}
            name = "synthetic_research_v1.csv" if core else "synthetic_sectors_v1.csv"
            content = files("cyclescope.data").joinpath(name).read_text()
            bars = tuple(
                DailyBar.model_validate({**row, "volume": int(row["volume"])})
                for row in csv.DictReader(io.StringIO(content))
                if row["symbol"] == symbol
            )
            version = self.provider_id if core else "synthetic-sectors-v1"
        else:
            fixture = json.loads(files("cyclescope.data").joinpath("synthetic_v1.json").read_text())
            if symbol not in fixture["bars"]:
                raise InsufficientData("Sector fixtures require the synthetic_research provider")
            bars = tuple(DailyBar.model_validate(row) for row in fixture["bars"][symbol])
            version = fixture["version"]
        return BarBatch(
            symbol=symbol,
            provider=self.provider_id,
            data_kind=self.data_kind,
            data_version=version,
            fetched_at=datetime.now(UTC),
            bars=tuple(bar for bar in bars if period.start <= bar.session_date <= period.end),
        )
