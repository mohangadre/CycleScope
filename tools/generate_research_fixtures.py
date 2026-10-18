"""Invented reproducible 40/120-session mixed signals, never real equity observations."""

import argparse
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import numpy as np

from cyclescope.domain.calendar import session_dates
from cyclescope.domain.models import CORE_CATALOG, DailyBar, DateRange


def generate(target: Path) -> None:
    dates = session_dates(DateRange(start=date(2020, 1, 2), end=date(2024, 12, 31)))[:720]
    with target.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["symbol", "session_date", "open", "high", "low", "close", "volume"],
            lineterminator="\n",
        )
        writer.writeheader()
        for index, instrument in enumerate(CORE_CATALOG):
            rng = np.random.default_rng(1729 + index)
            t = np.arange(len(dates))
            log_prices = (
                np.log(100 + 25 * index)
                + 0.0002 * t
                + 0.04 * np.sin(2 * np.pi * t / 40)
                + 0.025 * np.cos(2 * np.pi * t / 120)
                + rng.normal(0, 0.003, len(t))
            )
            volumes = rng.integers(950000, 1050001, size=len(t))
            for session, price, volume in zip(dates, np.exp(log_prices), volumes, strict=True):
                close = Decimal(f"{price:.8f}")
                opening = (close * Decimal("0.999")).quantize(Decimal("0.00000001"))
                bar = DailyBar(
                    symbol=instrument.symbol,
                    session_date=session,
                    open=opening,
                    high=(close * Decimal("1.002")).quantize(Decimal("0.00000001")),
                    low=(opening * Decimal("0.998")).quantize(Decimal("0.00000001")),
                    close=close,
                    volume=int(volume),
                )
                writer.writerow(bar.model_dump(mode="json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "src/cyclescope/data/synthetic_research_v1.csv",
    )
    generate(parser.parse_args().output)
