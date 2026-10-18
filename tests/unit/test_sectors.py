import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from cyclescope.analytics.sectors import classify, rotation
from cyclescope.analytics.series import PriceSeries
from cyclescope.domain.calendar import trailing_sessions
from cyclescope.domain.errors import InsufficientData
from cyclescope.domain.models import SECTOR_CATALOG
from cyclescope.domain.sectors import SectorRequest
from cyclescope.providers.synthetic import SyntheticProvider


def panel(n: int = 240, slope: float = 0.001) -> dict[str, PriceSeries]:
    dates = trailing_sessions(date(2024, 12, 31), n)
    t = np.arange(n)
    benchmark = 100 * np.exp(0.0003 * t)
    result = {"SPY": PriceSeries(dates, tuple(benchmark.tolist()))}
    for instrument in SECTOR_CATALOG:
        result[instrument.symbol] = PriceSeries(
            dates, tuple((benchmark * 2 * np.exp(slope * t)).tolist())
        )
    return result


@pytest.mark.parametrize(
    "strength,momentum,expected",
    [
        (0.1, 0.02, "leading"),
        (-0.1, 0.02, "improving"),
        (0.1, -0.02, "weakening"),
        (-0.1, -0.02, "lagging"),
        (0, 0.02, "neutral"),
        (0.1, 0, "neutral"),
        (1e-13, 0.02, "neutral"),
    ],
)
def test_quadrants_and_explicit_axis_ties(strength: float, momentum: float, expected: str) -> None:
    assert classify(strength, momentum) == expected


@pytest.mark.parametrize("smoothing", [1, 5, 30])
def test_analytic_ratios_normalization_and_trailing_momentum(smoothing: int) -> None:
    data = panel()
    config = SectorRequest(
        as_of=data["SPY"].dates[-1],
        lookback_sessions=100,
        momentum_sessions=20,
        smoothing_sessions=smoothing,
    )
    result = rotation(data, config)
    series = result.sectors[0]
    assert len(series.points) == 100
    assert result.normalization_session == data["SPY"].dates[-100]
    for i, point in enumerate(series.points):
        original_offset = len(data["SPY"].dates) - 100 + i
        assert point.relative_strength == pytest.approx(2 * np.exp(0.001 * original_offset))
        assert point.normalized_rs == pytest.approx(100 * np.exp(0.001 * i))
        assert point.smoothed_normalized_rs == pytest.approx(100 * np.exp(0.001 * i))
        assert point.momentum_log_rs == pytest.approx(0.02)
        assert point.relative_change_percent == pytest.approx(100 * np.expm1(0.02))
    assert series.points[0].quadrant == "neutral"
    assert series.points[-1].quadrant == "leading"


def test_constant_ratio_is_neutral_and_common_market_movement_cancels() -> None:
    data = panel(slope=0)
    result = rotation(data, SectorRequest(as_of=data["SPY"].dates[-1]))
    assert all(point.quadrant == "neutral" for sector in result.sectors for point in sector.points)
    assert all(
        point.normalized_rs == pytest.approx(100)
        for sector in result.sectors
        for point in sector.points
    )
    assert all(
        point.relative_strength == pytest.approx(2)
        for sector in result.sectors
        for point in sector.points
    )


def test_smoothing_is_exact_backward_log_average_not_centered_or_arithmetic() -> None:
    data = panel(slope=0)
    n = len(data["SPY"].dates)
    relative_logs = 0.02 * np.sin(np.arange(n) / 7) + np.arange(n) ** 2 * 0.00001
    prices = np.asarray(data["SPY"].closes) * np.exp(relative_logs)
    data["XLK"] = PriceSeries(data["SPY"].dates, tuple(prices.tolist()))
    result = rotation(
        data,
        SectorRequest(
            as_of=data["SPY"].dates[-1],
            lookback_sessions=100,
            momentum_sessions=10,
            smoothing_sessions=5,
        ),
    )
    points = result.sectors[0].points
    z_now = float(np.mean(relative_logs[-5:]))
    z_prev = float(np.mean(relative_logs[-15:-10]))
    z_base = float(np.mean(relative_logs[-104:-99]))
    assert points[-1].momentum_log_rs == pytest.approx(z_now - z_prev)
    assert points[-1].smoothed_normalized_rs == pytest.approx(100 * np.exp(z_now - z_base))


def test_future_append_and_corruption_cannot_change_any_sector_value() -> None:
    data = panel()
    cutoff = data["SPY"].dates[-31]
    config = SectorRequest(as_of=cutoff, lookback_sessions=100)
    prefix = {
        symbol: PriceSeries(series.dates[:-30], series.closes[:-30])
        for symbol, series in data.items()
    }
    corrupt = {
        symbol: PriceSeries(series.dates, series.closes[:-30] + (float("nan"),) * 30)
        for symbol, series in data.items()
    }
    assert rotation(prefix, config) == rotation(data, config) == rotation(corrupt, config)


@pytest.mark.parametrize(
    "fault", ["missing_symbol", "gap", "zero", "nan", "duplicates", "too_short"]
)
def test_invalid_or_unaligned_panels_fail_clearly(fault: str) -> None:
    data = panel()
    original = data["XLK"]
    if fault == "missing_symbol":
        del data["XLK"]
    elif fault == "gap":
        data["XLK"] = PriceSeries(
            original.dates[:-2] + original.dates[-1:], original.closes[:-2] + original.closes[-1:]
        )
    elif fault == "zero":
        data["XLK"] = PriceSeries(original.dates, original.closes[:-1] + (0,))
    elif fault == "nan":
        data["XLK"] = PriceSeries(original.dates, original.closes[:-1] + (float("nan"),))
    elif fault == "duplicates":
        data["XLK"] = PriceSeries(original.dates[:-1] + (original.dates[-2],), original.closes)
    else:
        data["XLK"] = PriceSeries(original.dates[-40:], original.closes[-40:])
    with pytest.raises(InsufficientData):
        rotation(data, SectorRequest(as_of=original.dates[-1]))


@pytest.mark.parametrize(
    "change",
    [
        {"lookback_sessions": 31},
        {"lookback_sessions": 1261},
        {"momentum_sessions": 0},
        {"smoothing_sessions": 31},
        {"smoothing_sessions": 1.5},
    ],
)
def test_bounded_configs(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SectorRequest.model_validate({"as_of": "2024-12-31", **change})


def test_sector_fixture_regenerates_and_original_profiles_remain_unchanged(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    output = tmp_path / "sectors.csv"
    subprocess.run(
        [sys.executable, str(root / "tools/generate_sector_fixtures.py"), "--output", str(output)],
        check=True,
    )
    assert (
        output.read_bytes() == (root / "src/cyclescope/data/synthetic_sectors_v1.csv").read_bytes()
    )
    provider = SyntheticProvider(research=True)
    for instrument in SECTOR_CATALOG:
        batch = provider.get_daily_bars(instrument.symbol, date(2020, 1, 2), date(2022, 11, 8))
        assert len(batch.bars) == 720
        assert batch.data_kind == "synthetic"
        assert batch.data_version == "synthetic-sectors-v1"
    with pytest.raises(InsufficientData, match="research"):
        SyntheticProvider().get_daily_bars("XLK", date(2024, 1, 2), date(2024, 3, 28))


def test_calendar_window_respects_holiday_and_boundaries() -> None:
    assert trailing_sessions(date(2024, 1, 15), 2) == (date(2024, 1, 11), date(2024, 1, 12))
    with pytest.raises(InsufficientData):
        trailing_sessions(date(1990, 1, 2), 100)
    with pytest.raises(InsufficientData):
        trailing_sessions(date(2024, 1, 15), 2521)
