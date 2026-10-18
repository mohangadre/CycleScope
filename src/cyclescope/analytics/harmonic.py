"""Training-only harmonic regression with a bounded, uncalibrated residual bootstrap."""

from datetime import date
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.signal import find_peaks

from cyclescope.analytics.fitting import bootstrap_coefficients, design_matrix, fit_harmonics
from cyclescope.analytics.fourier import analyze_cycles
from cyclescope.analytics.series import PriceSeries
from cyclescope.domain.analysis import (
    ForecastPoint,
    ForecastResult,
    HarmonicConfig,
    HarmonicFit,
    TurningPoint,
    UncertaintyMethod,
)
from cyclescope.domain.calendar import future_sessions
from cyclescope.domain.errors import InsufficientData


def positive_prices(log_values: NDArray[np.float64]) -> NDArray[np.float64]:
    try:
        with np.errstate(over="raise", invalid="raise", under="ignore"):
            prices = np.exp(log_values)
    except FloatingPointError as exc:
        raise InsufficientData(
            "Numerically unstable projection; shorten horizon or change training configuration"
        ) from exc
    if not np.all(np.isfinite(prices)) or np.any(prices <= 0):
        raise InsufficientData("Projection produced invalid prices")
    return prices


def turning_points(
    log_projection: NDArray[np.float64], sessions: tuple[date, ...], config: HarmonicConfig
) -> tuple[TurningPoint, ...]:
    events: list[TurningPoint] = []
    numerical_floor = 64 * np.finfo(float).eps * max(1.0, float(np.max(np.abs(log_projection))))
    prominence = max(numerical_floor, config.turn_prominence_log_price)
    kinds: tuple[Literal["peak", "trough"], ...] = ("peak", "trough")
    for kind in kinds:
        values = log_projection if kind == "peak" else -log_projection
        positions, _ = find_peaks(
            values, distance=config.turn_min_separation_sessions, prominence=prominence
        )
        for position in positions:
            index = int(position)
            left = max(0, index - config.turn_window_tolerance_sessions)
            right = min(len(sessions) - 1, index + config.turn_window_tolerance_sessions)
            events.append(
                TurningPoint(
                    kind=kind,
                    session_offset=index + 1,
                    session_date=sessions[index],
                    window_start_offset=left + 1,
                    window_end_offset=right + 1,
                    window_start=sessions[left],
                    window_end=sessions[right],
                )
            )
    return tuple(sorted(events, key=lambda event: (event.session_offset, event.kind)))


def forecast(
    series: PriceSeries, as_of: date, lookback: int, horizon: int, config: HarmonicConfig
) -> ForecastResult:
    training = series.through(as_of, lookback)
    sessions = future_sessions(training.dates[-1], horizon)
    cycle_result = analyze_cycles(training, as_of, lookback, config.fft)
    cycles = cycle_result.analysis.cycles[: config.max_harmonics]
    periods = tuple(cycle.period_sessions for cycle in cycles)
    y = training.log_prices()
    n = len(y)
    scale = n - 1
    solution = fit_harmonics(y, periods, cycle_result.analysis.sample_count, config)
    x = solution.design
    fit_map = solution.fit_map
    coefficients = solution.coefficients
    periods = solution.refinement.fitted_periods_sessions
    future_x = design_matrix(np.arange(n, n + horizon, dtype=np.float64), periods, scale)
    if not np.all(np.isfinite(coefficients)):
        raise InsufficientData("Harmonic coefficients are not finite")
    fitted = x @ coefficients
    residuals = y - fitted
    residuals -= np.mean(residuals)
    delta_x = future_x - x[-1]
    observed_origin = float(y[-1])
    fitted_origin = float(fitted[-1])
    projected = observed_origin + delta_x @ coefficients
    prices = positive_prices(projected)

    # One local RNG. Circular blocks preserve short residual dependence. No test
    # observation enters period selection, fit, bootstrap, or quantiles.
    rng = np.random.default_rng(config.seed)
    block = min(config.bootstrap_block_sessions, n)
    starts = rng.integers(0, n, size=(config.bootstrap_draws, (n + horizon + block - 1) // block))
    indices = ((starts[:, :, None] + np.arange(block)) % n).reshape(config.bootstrap_draws, -1)[
        :, : n + horizon
    ]
    sampled = residuals[indices]
    coefficient_draws = bootstrap_coefficients(coefficients, fit_map, sampled[:, :n])
    predictive_logs = (
        observed_origin + delta_x @ coefficient_draws + sampled[:, n:].T - sampled[:, n - 1]
    )
    tail = (1 - config.residual_quantile_mass) / 2
    bounds = positive_prices(np.quantile(predictive_logs, [tail, 1 - tail], axis=1))
    warnings = [
        "exploratory_forecast_not_investment_advice",
        "uncertainty_coverage_not_evaluated",
        "historical_adjustments_not_point_in_time_guaranteed",
        "frequency_selection_and_refinement_uncertainty_not_included",
    ]
    if not cycles:
        warnings.append("no_candidate_cycles_fitted_trend_only")
    return ForecastResult(
        as_of=as_of,
        forecast_origin=training.dates[-1],
        train_start=training.dates[0],
        train_end=training.dates[-1],
        training_sample_count=n,
        horizon_sessions=horizon,
        last_observed_price=training.closes[-1],
        config=config,
        fit=HarmonicFit(
            periods_sessions=periods,
            coefficients=tuple(coefficients.tolist()),
            time_scale_sessions=scale,
            ridge_alpha=config.ridge_alpha,
            training_residual_rmse_log_price=float(np.sqrt(np.mean(residuals**2))),
            projection_method="conditional_fitted_change",
            observed_origin_log_price=observed_origin,
            fitted_origin_log_price=fitted_origin,
            origin_adjustment_log_price=observed_origin - fitted_origin,
            frequency_refinement=solution.refinement,
        ),
        selected_cycles=cycles,
        points=tuple(
            ForecastPoint(
                session_offset=i + 1,
                session_date=session,
                value=float(prices[i]),
                log_value=float(projected[i]),
                lower=float(bounds[0, i]),
                upper=float(bounds[1, i]),
            )
            for i, session in enumerate(sessions)
        ),
        turning_points=turning_points(projected, sessions, config),
        uncertainty=UncertaintyMethod(
            residual_quantile_mass=config.residual_quantile_mass,
            bootstrap_draws=config.bootstrap_draws,
            block_sessions=block,
            seed=config.seed,
        ),
        warnings=tuple(warnings),
    )
