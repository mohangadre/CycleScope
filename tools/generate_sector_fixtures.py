"""Invent eight sector histories relative to the unchanged research SPY fixture."""

import argparse
import csv
from decimal import Decimal
from pathlib import Path

import numpy as np

from cyclescope.domain.models import SECTOR_CATALOG, DailyBar


def generate(target: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "src/cyclescope/data"
    with (source / "synthetic_research_v1.csv").open() as stream:
        benchmark = [row for row in csv.DictReader(stream) if row["symbol"] == "SPY"]
    with target.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(benchmark[0]), lineterminator="\n")
        writer.writeheader()
        t = np.arange(len(benchmark))
        for index, instrument in enumerate(SECTOR_CATALOG):
            relative = (0.6 + 0.07 * index) * np.exp(
                0.06 * np.sin(2 * np.pi * t / 160 + index * np.pi / 4)
            )
            for row, ratio in zip(benchmark, relative, strict=True):
                close = Decimal(f"{float(row['close']) * ratio:.8f}")
                opening = (close * Decimal("0.999")).quantize(Decimal("0.00000001"))
                bar = DailyBar(
                    symbol=instrument.symbol,
                    session_date=row["session_date"],
                    open=opening,
                    close=close,
                    high=(close * Decimal("1.002")).quantize(Decimal("0.00000001")),
                    low=(opening * Decimal("0.998")).quantize(Decimal("0.00000001")),
                    volume=1000000 + index * 10000,
                )
                writer.writerow(bar.model_dump(mode="json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "src/cyclescope/data/synthetic_sectors_v1.csv",
    )
    generate(parser.parse_args().output)
