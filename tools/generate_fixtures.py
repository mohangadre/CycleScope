"""Reproduce the versioned example. Values are invented, never observed prices."""

import json
import math
from datetime import date
from decimal import Decimal
from pathlib import Path

from cyclescope.domain.calendar import session_dates
from cyclescope.domain.models import CORE_CATALOG, DateRange


def generate() -> dict[str, object]:
    dates = session_dates(DateRange(start=date(2024, 1, 2), end=date(2024, 3, 28)))
    series = {}
    for index, instrument in enumerate(CORE_CATALOG):
        bars = []
        for offset, session in enumerate(dates):
            close = Decimal(
                f"{100 + 25 * index + offset * 0.1 + 4 * math.sin(2 * math.pi * offset / 40):.4f}"
            )
            opening = close - Decimal("0.25")
            bars.append(
                {
                    "symbol": instrument.symbol,
                    "session_date": session.isoformat(),
                    "open": str(opening),
                    "high": str(close + Decimal("0.75")),
                    "low": str(opening - Decimal("0.75")),
                    "close": str(close),
                    "volume": 1000000 + index * 10000 + offset * 100,
                }
            )
        series[instrument.symbol] = bars
    return {
        "version": "synthetic-v1",
        "data_kind": "synthetic",
        "description": "Invented OHLCV; XNYS session dates; not observed stock prices",
        "bars": series,
    }


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "src/cyclescope/data/synthetic_v1.json"
    target.write_text(json.dumps(generate(), indent=2) + "\n")
