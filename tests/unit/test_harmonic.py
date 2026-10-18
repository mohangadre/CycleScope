from datetime import date

import numpy as np
import pytest
from pydantic import ValidationError

from cyclescope.analytics.harmonic import forecast, positive_prices
from cyclescope.analytics.series import PriceSeries
from cyclescope.domain.analysis import FFTConfig, HarmonicConfig
from cyclescope.domain.calendar import future_sessions, session_dates
from cyclescope.domain.errors import InsufficientData
from cyclescope.domain.models import DateRange


def series(n: int = 720, noise: float = 0) -> PriceSeries:
    dates = session_dates(DateRange(start=date(2020, 1, 2), end=date(2024, 12, 31)))[:n]
    t = np.arange(n)
    log_values = 4 + 0.04 * np.sin(2 * np.pi * t / 40)
    log_values += np.random.default_rng(6).normal(0, noise, n)
    return PriceSeries(dates, tuple(np.exp(log_values).tolist()))


def exact_config() -> HarmonicConfig:
    return HarmonicConfig(
        fft=FFTConfig(window="boxcar", detrend="constant", max_peaks=1), ridge_alpha=0
    )


def test_exact_harmonic_projection_and_future_only_turning_points() -> None:
    data = series(480)
    result = forecast(data, data.dates[-1], 480, 80, exact_config())
    expected = 4 + 0.04 * np.sin(2 * np.pi * np.arange(480, 560) / 40)
    assert np.array([point.log_value for point in result.points]) == pytest.approx(
        expected, abs=1e-12
    )
    assert result.fit.periods_sessions == (40,)
    assert [(event.kind, event.session_offset) for event in result.turning_points] == [
        ("peak", 11),
        ("trough", 31),
        ("peak", 51),
        ("trough", 71),
    ]
    assert all(point.session_date > result.forecast_origin for point in result.points)
    for event in result.turning_points:
        assert event.window_start > result.forecast_origin
        assert event.window_start_offset <= event.session_offset <= event.window_end_offset
        assert event.window_method == "heuristic_session_tolerance"


def test_append_modify_and_corrupt_future_leave_model_forecast_and_bands_unchanged() -> None:
    full = series()
    cutoff = full.dates[479]
    prefix = PriceSeries(full.dates[:480], full.closes[:480])
    changed = PriceSeries(full.dates, full.closes[:480] + (float("nan"),) * 240)
    config = HarmonicConfig(seed=99)
    reference = forecast(prefix, cutoff, 480, 30, config)
    assert reference == forecast(full, cutoff, 480, 30, config)
    assert reference == forecast(changed, cutoff, 480, 30, config)


def test_seeded_bootstrap_is_reproducible_and_explicitly_uncalibrated() -> None:
    data = series(360, noise=0.01)
    config = HarmonicConfig(seed=7, bootstrap_draws=100)
    result = forecast(data, data.dates[-1], 360, 20, config)
    assert result == forecast(data, data.dates[-1], 360, 20, config)
    other = forecast(data, data.dates[-1], 360, 20, config.model_copy(update={"seed": 8}))
    assert result.fit == other.fit
    assert any(a.lower != b.lower for a, b in zip(result.points, other.points, strict=True))
    assert result.uncertainty.calibrated is False
    assert result.uncertainty.label == "exploratory_uncalibrated_band"
    assert all(0 < point.lower <= point.upper for point in result.points)
    assert "NaN" not in result.model_dump_json()


def test_constant_series_is_finite_and_has_no_spurious_extrema() -> None:
    data = series(100)
    data = PriceSeries(data.dates, (100.0,) * 100)
    result = forecast(data, data.dates[-1], 100, 20, HarmonicConfig())
    assert result.fit.periods_sessions == ()
    assert result.turning_points == ()
    assert all(point.value == pytest.approx(100) for point in result.points)
    assert "no_candidate_cycles_fitted_trend_only" in result.warnings


def test_real_session_dates_cross_holiday_and_weekend() -> None:
    assert future_sessions(date(2024, 1, 12), 2) == (date(2024, 1, 16), date(2024, 1, 17))
    data = series(720)
    weekend = date(2021, 11, 27)
    # Use a self-contained training series ending on the prior exchange session.
    available = [
        (day, price) for day, price in zip(data.dates, data.closes, strict=True) if day <= weekend
    ]
    training = PriceSeries(
        tuple(day for day, _ in available), tuple(price for _, price in available)
    )
    result = forecast(training, weekend, 100, 2, HarmonicConfig())
    assert result.forecast_origin < weekend
    assert result.points[0].session_date == date(2021, 11, 29)


@pytest.mark.parametrize("horizon", [0, -1, 127])
def test_invalid_horizon(horizon: int) -> None:
    data = series(100)
    with pytest.raises(InsufficientData, match="horizon"):
        forecast(data, data.dates[-1], 100, horizon, HarmonicConfig())


@pytest.mark.parametrize(
    "change",
    [
        {"ridge_alpha": -1},
        {"seed": -1},
        {"bootstrap_draws": 501},
        {"max_harmonics": 4},
        {"ridge_alpha": float("nan")},
        {"bootstrap_block_sessions": 0},
        {"residual_quantile_mass": 1},
    ],
)
def test_bound_model_configuration(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        HarmonicConfig.model_validate(change)


def test_numeric_overflow_is_a_clear_error() -> None:
    with pytest.raises(InsufficientData, match="unstable"):
        positive_prices(np.array([1000.0]))


def test_forecast_calendar_limit() -> None:
    dates = session_dates(DateRange(start=date(2035, 1, 2), end=date(2035, 12, 31)))
    data = PriceSeries(dates, (100.0,) * len(dates))
    with pytest.raises(InsufficientData, match="calendar"):
        forecast(data, dates[-1], 100, 20, HarmonicConfig())
