"""Pure selection and validation of uniformly spaced exchange-session observations."""

from dataclasses import dataclass
from datetime import date

import numpy as np
from numpy.typing import NDArray

from cyclescope.domain.calendar import session_dates, session_on_or_before
from cyclescope.domain.errors import InsufficientData
from cyclescope.domain.models import DateRange

MIN_SAMPLES = 32
MAX_SAMPLES = 2520


@dataclass(frozen=True)
class PriceSeries:
    dates: tuple[date, ...]
    closes: tuple[float, ...]

    def validate(self) -> None:
        if not self.dates or len(self.dates) != len(self.closes):
            raise InsufficientData("Require matching nonempty price and session-date arrays")
        if len(self.dates) > MAX_SAMPLES:
            raise InsufficientData(f"At most {MAX_SAMPLES} observations are supported")
        if self.dates != tuple(sorted(set(self.dates))):
            raise InsufficientData("Session dates must be unique and strictly increasing")
        expected = session_dates(DateRange(start=self.dates[0], end=self.dates[-1]))
        if self.dates != expected:
            raise InsufficientData("Prices must cover consecutive exchange sessions without gaps")
        values = np.asarray(self.closes, dtype=np.float64)
        if not np.all(np.isfinite(values)) or np.any(values <= 0):
            raise InsufficientData("Adjusted close must be positive and finite")

    def through(self, as_of: date, lookback: int) -> "PriceSeries":
        if len(self.dates) != len(self.closes):
            raise InsufficientData("Price/date array lengths differ")
        if not MIN_SAMPLES <= lookback <= MAX_SAMPLES:
            raise InsufficientData(f"lookback must be {MIN_SAMPLES}–{MAX_SAMPLES} sessions")
        # Filter BEFORE validation, log transforms, detrending, selection, or fitting.
        selected = [
            (day, price) for day, price in zip(self.dates, self.closes, strict=True) if day <= as_of
        ]
        selected = selected[-lookback:]
        if len(selected) != lookback:
            raise InsufficientData(f"Need {lookback} observations on or before as_of")
        result = PriceSeries(
            tuple(day for day, _ in selected), tuple(price for _, price in selected)
        )
        result.validate()
        if result.dates[-1] != session_on_or_before(as_of):
            raise InsufficientData("Stored data does not reach the requested forecast cutoff")
        return result

    def log_prices(self) -> NDArray[np.float64]:
        return np.log(np.asarray(self.closes, dtype=np.float64))
