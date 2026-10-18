"""Analytic regressions for forecasts made between the original FFT grid bins.

These are signal-recovery and conditioning checks, not assertions about financial
forecast skill or improvements on the previously inspected market backtest.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from numpy.typing import NDArray
from pydantic import ValidationError

from cyclescope.analytics.harmonic import forecast
from cyclescope.analytics.series import PriceSeries
from cyclescope.domain.analysis import FFTConfig, HarmonicConfig, HarmonicFit
from cyclescope.domain.calendar import session_dates
from cyclescope.domain.models import DateRange


def analytic_log_prices(
    offsets: NDArray[np.float64],
    periods: tuple[float, float] = (40.0, 120.0),
    phases: tuple[float, float] = (0.0, 0.7),
) -> NDArray[np.float64]:
    return (
        4.0
        + 0.0002 * offsets
        + 0.04 * np.sin(2 * np.pi * offsets / periods[0] + phases[0])
        + 0.025 * np.cos(2 * np.pi * offsets / periods[1] + phases[1])
    )


def price_series(log_prices: NDArray[np.float64]) -> PriceSeries:
    dates = session_dates(DateRange(start=date(2020, 1, 2), end=date(2024, 12, 31)))
    return PriceSeries(dates[: len(log_prices)], tuple(np.exp(log_prices).tolist()))


def recorded_curve(fit: HarmonicFit, offset: int) -> float:
    """Evaluate the documented saved coefficient contract without the fit helper."""
    value = fit.coefficients[0] + fit.coefficients[1] * offset / fit.time_scale_sessions
    for i, period in enumerate(fit.periods_sessions):
        angle = 2 * np.pi * offset / period
        value += fit.coefficients[2 + 2 * i] * np.cos(angle)
        value += fit.coefficients[3 + 2 * i] * np.sin(angle)
    return float(value)


@pytest.mark.parametrize("n", [500, 520])
@pytest.mark.parametrize("phases", [(0.0, 0.7), (1.1, -0.4)])
def test_default_model_recovers_cycles_between_fft_bins(
    n: int, phases: tuple[float, float]
) -> None:
    training = price_series(analytic_log_prices(np.arange(n, dtype=np.float64), phases=phases))
    result = forecast(training, training.dates[-1], n, 60, HarmonicConfig())
    expected = analytic_log_prices(np.arange(n, n + 60, dtype=np.float64), phases=phases)

    # The .01 ridge penalty intentionally biases the noiseless fit slightly. The
    # error bound is still <0.5% of the smaller synthetic cycle's amplitude.
    assert [point.log_value for point in result.points] == pytest.approx(expected, abs=0.0001)
    for expected_period in (40.0, 120.0):
        closest = min(result.fit.periods_sessions, key=lambda p: abs(p - expected_period))
        assert closest == pytest.approx(expected_period, rel=0.001)
    assert result.fit.model_version == "harmonic-increment-log-price-v2"


@pytest.mark.parametrize("phases", [(0.0, 0.7), (1.1, -0.4)])
def test_noninteger_periods_are_recovered_without_rounding_to_fft_grid(
    phases: tuple[float, float],
) -> None:
    n, horizon = 517, 60
    periods = (37.3, 113.7)
    training = price_series(
        analytic_log_prices(np.arange(n, dtype=np.float64), periods=periods, phases=phases)
    )
    result = forecast(training, training.dates[-1], n, horizon, HarmonicConfig(ridge_alpha=0))
    expected = analytic_log_prices(
        np.arange(n, n + horizon, dtype=np.float64), periods=periods, phases=phases
    )

    assert [point.log_value for point in result.points] == pytest.approx(expected, abs=0.000002)
    assert sorted(result.fit.periods_sessions) == pytest.approx(periods, rel=0.00001)
    # Cycle analysis continues to describe the observed spectrum; fitted model
    # frequencies carry their separate refinement metadata.
    assert any(abs(n / period - round(n / period)) > 0.01 for period in result.fit.periods_sessions)


def test_saved_model_reconstructs_conditional_changes_and_origin() -> None:
    n = 500
    log_prices = analytic_log_prices(np.arange(n, dtype=np.float64))
    log_prices[-1] += 0.12  # A large terminal residual must not create a reset in level.
    training = price_series(log_prices)
    result = forecast(training, training.dates[-1], n, 30, HarmonicConfig())
    fit = result.fit
    fitted_origin = recorded_curve(fit, n - 1)
    observed_origin = float(log_prices[-1])

    assert abs(observed_origin - fitted_origin) > 0.05
    assert fit.projection_method == "conditional_fitted_change"
    assert fit.observed_origin_log_price == pytest.approx(observed_origin)
    assert fit.fitted_origin_log_price == pytest.approx(fitted_origin)
    assert fit.origin_adjustment_log_price == pytest.approx(observed_origin - fitted_origin)
    # Offset zero is deliberately not a forecast point; the documented formula
    # nevertheless starts at exactly the observation known at the cutoff.
    assert observed_origin + recorded_curve(fit, n - 1) - fitted_origin == pytest.approx(
        observed_origin, abs=1e-14
    )
    for point in result.points:
        expected_change = recorded_curve(fit, n - 1 + point.session_offset) - fitted_origin
        assert point.log_value - observed_origin == pytest.approx(expected_change, abs=1e-12)
        assert point.value == pytest.approx(np.exp(point.log_value), rel=1e-12)
        assert 0 < point.lower <= point.upper


def test_noiseless_trend_extrapolates_from_observed_origin_without_spurious_cycles() -> None:
    n, horizon, slope = 517, 40, 0.0007
    training = price_series(4.0 + slope * np.arange(n, dtype=np.float64))
    result = forecast(training, training.dates[-1], n, horizon, HarmonicConfig(ridge_alpha=0))

    assert result.fit.periods_sessions == ()
    assert result.turning_points == ()
    assert [point.log_value for point in result.points] == pytest.approx(
        4.0 + slope * np.arange(n, n + horizon), abs=1e-12
    )
    assert result.fit.frequency_refinement is not None
    assert result.fit.frequency_refinement.status == "no_cycles"


def test_frequency_refinement_respects_training_bin_and_period_bounds() -> None:
    n = 517
    training = price_series(
        analytic_log_prices(np.arange(n, dtype=np.float64), periods=(37.3, 113.7))
    )
    result = forecast(training, training.dates[-1], n, 20, HarmonicConfig(ridge_alpha=0))
    refinement = result.fit.frequency_refinement
    assert refinement is not None
    assert refinement.status == "refined"
    assert refinement.method == "bounded_variable_projection"
    assert refinement.nfev <= result.config.frequency_refinement_max_nfev
    assert refinement.final_objective <= refinement.initial_objective
    assert refinement.fitted_periods_sessions == result.fit.periods_sessions
    assert refinement.initial_periods_sessions == tuple(
        cycle.period_sessions for cycle in result.selected_cycles
    )
    for initial, fitted, bounds in zip(
        refinement.initial_periods_sessions,
        refinement.fitted_periods_sessions,
        refinement.frequency_bounds,
        strict=True,
    ):
        low, high = bounds
        assert low >= 1 / initial - 0.5 / n - 1e-14
        assert high <= 1 / initial + 0.5 / n + 1e-14
        assert low >= result.config.fft.min_repetitions / n - 1e-14
        assert high <= 1 / result.config.fft.min_period_sessions + 1e-14
        assert low - 1e-14 <= 1 / fitted <= high + 1e-14


def test_disabled_refinement_preserves_original_fft_frequencies() -> None:
    n = 517
    training = price_series(
        analytic_log_prices(np.arange(n, dtype=np.float64), periods=(37.3, 113.7))
    )
    result = forecast(training, training.dates[-1], n, 20, HarmonicConfig(refine_frequencies=False))

    assert result.fit.periods_sessions == tuple(
        cycle.period_sessions for cycle in result.selected_cycles
    )
    assert result.fit.frequency_refinement is not None
    assert result.fit.frequency_refinement.status == "disabled"


@pytest.mark.parametrize(
    "failure,status",
    [
        ("not_converged", "fallback_not_converged"),
        ("linear_algebra", "fallback_numerical_failure"),
    ],
)
def test_failed_refinement_preserves_finite_original_fit_and_forecast(
    monkeypatch: pytest.MonkeyPatch, failure: str, status: str
) -> None:
    n = 517
    training = price_series(
        analytic_log_prices(np.arange(n, dtype=np.float64), periods=(37.3, 113.7))
    )
    config = HarmonicConfig(seed=31)
    reference = forecast(
        training, training.dates[-1], n, 30, config.model_copy(update={"refine_frequencies": False})
    )
    solver = (
        Mock(return_value=SimpleNamespace(success=False, nfev=10))
        if failure == "not_converged"
        else Mock(side_effect=np.linalg.LinAlgError("Synthetic solver failure"))
    )
    monkeypatch.setattr("cyclescope.analytics.fitting.least_squares", solver)
    result = forecast(training, training.dates[-1], n, 30, config)

    solver.assert_called_once()
    assert result.fit.periods_sessions == reference.fit.periods_sessions
    assert result.fit.coefficients == reference.fit.coefficients
    assert result.points == reference.points  # Includes every bootstrap bound.
    assert result.turning_points == reference.turning_points
    assert result.fit.frequency_refinement is not None
    assert result.fit.frequency_refinement.status == status
    assert (
        result.fit.frequency_refinement.final_objective
        == result.fit.frequency_refinement.initial_objective
    )
    assert "NaN" not in result.model_dump_json()


def test_refinement_clips_frequency_search_at_explicit_period_limits() -> None:
    n = 480
    training = price_series(analytic_log_prices(np.arange(n, dtype=np.float64)))
    config = HarmonicConfig(
        fft=FFTConfig(min_period_sessions=40, max_period_sessions=120, max_peaks=2),
        max_harmonics=2,
    )
    result = forecast(training, training.dates[-1], n, 30, config)
    refinement = result.fit.frequency_refinement

    assert refinement is not None
    assert len(refinement.frequency_bounds) == 2
    assert min(low for low, _ in refinement.frequency_bounds) == pytest.approx(1 / 120)
    assert max(high for _, high in refinement.frequency_bounds) == pytest.approx(1 / 40)
    for period, (low, high) in zip(
        result.fit.periods_sessions, refinement.frequency_bounds, strict=True
    ):
        assert 1 / 120 <= low <= 1 / period <= high <= 1 / 40


def test_log_returns_refinement_uses_differenced_sample_count_for_bin_bounds() -> None:
    n = 517
    training = price_series(
        analytic_log_prices(np.arange(n, dtype=np.float64), periods=(37.3, 113.7))
    )
    result = forecast(
        training,
        training.dates[-1],
        n,
        30,
        HarmonicConfig(fft=FFTConfig(input="log_returns")),
    )
    refinement = result.fit.frequency_refinement
    assert refinement is not None
    assert refinement.frequency_bounds
    for initial, fitted, (low, high) in zip(
        refinement.initial_periods_sessions,
        refinement.fitted_periods_sessions,
        refinement.frequency_bounds,
        strict=True,
    ):
        assert (n - 1) / initial == pytest.approx(round((n - 1) / initial), abs=1e-12)
        assert low == pytest.approx(1 / initial - 0.5 / (n - 1), abs=1e-14)
        assert high == pytest.approx(1 / initial + 0.5 / (n - 1), abs=1e-14)
        assert low <= 1 / fitted <= high


def test_nyquist_with_collapsed_frequency_bounds_needs_no_optimizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    n, horizon = 128, 10
    training = price_series(4.0 + 0.04 * (-1.0) ** np.arange(n))
    config = HarmonicConfig(
        fft=FFTConfig(
            min_period_sessions=2,
            max_period_sessions=2,
            window="boxcar",
            detrend="constant",
            max_peaks=1,
        ),
        max_harmonics=1,
        ridge_alpha=0,
    )
    solver = Mock(side_effect=AssertionError("A fixed Nyquist frequency cannot be optimized"))
    monkeypatch.setattr("cyclescope.analytics.fitting.least_squares", solver)
    result = forecast(training, training.dates[-1], n, horizon, config)

    solver.assert_not_called()
    assert result.fit.periods_sessions == (2.0,)
    assert result.fit.frequency_refinement is not None
    assert result.fit.frequency_refinement.status == "unchanged"
    assert result.fit.frequency_refinement.frequency_bounds == ((0.5, 0.5),)
    assert result.fit.frequency_refinement.nfev == 0
    assert [point.log_value for point in result.points] == pytest.approx(
        4.0 + 0.04 * (-1.0) ** np.arange(n, n + horizon), abs=1e-12
    )


def test_refinement_origin_adjustment_and_bands_ignore_corrupt_future() -> None:
    n, full_count = 517, 650
    log_prices = analytic_log_prices(np.arange(full_count, dtype=np.float64), periods=(37.3, 113.7))
    log_prices += np.random.default_rng(91).normal(0, 0.003, full_count)
    full = price_series(log_prices)
    training = PriceSeries(full.dates[:n], full.closes[:n])
    corrupt = PriceSeries(full.dates, full.closes[:n] + (float("nan"),) * (full_count - n))
    config = HarmonicConfig(seed=123)
    expected = forecast(training, training.dates[-1], n, 40, config)

    assert forecast(full, training.dates[-1], n, 40, config) == expected
    assert forecast(corrupt, training.dates[-1], n, 40, config) == expected
    assert "NaN" not in expected.model_dump_json()


def test_residual_bootstrap_is_centered_on_fitted_parameters_without_reapplying_ridge() -> None:
    from cyclescope.analytics.fitting import bootstrap_coefficients

    n = 64
    offsets = np.arange(n, dtype=np.float64)
    design = np.column_stack([np.ones(n), offsets / (n - 1), np.cos(2 * np.pi * offsets / 16)])
    # Strong regularization makes an erroneous second shrink visible even with
    # zero residuals; antithetic residuals separately check bootstrap centering.
    fit_map = np.linalg.solve(design.T @ design + np.diag([0.0, 1000.0, 1000.0]), design.T)
    parameters = fit_map @ (4.0 + 0.2 * offsets / (n - 1) + 0.1 * np.cos(2 * np.pi * offsets / 16))
    noiseless = bootstrap_coefficients(parameters, fit_map, np.zeros((8, n)))
    assert noiseless.shape == (3, 8)
    assert noiseless == pytest.approx(np.repeat(parameters[:, None], 8, axis=1), abs=1e-14)
    noise = np.random.default_rng(18).normal(0, 0.01, (8, n))
    draws = bootstrap_coefficients(parameters, fit_map, np.concatenate([noise, -noise]))
    assert np.mean(draws, axis=1) == pytest.approx(parameters, abs=1e-14)


@pytest.mark.parametrize(
    "change",
    [
        {"frequency_refinement_max_nfev": 9},
        {"frequency_refinement_max_nfev": 201},
        {"frequency_refinement_max_nfev": 10.5},
    ],
)
def test_refinement_configuration_rejects_invalid_workload_controls(
    change: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        HarmonicConfig.model_validate(change)
