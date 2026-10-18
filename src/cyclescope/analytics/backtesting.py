"""Ordered walk-forward evaluation: every fold selects, fits, and bootstraps anew."""

import hashlib
import json
from collections.abc import Sequence

import numpy as np

from cyclescope.analytics.harmonic import forecast
from cyclescope.analytics.series import PriceSeries
from cyclescope.domain.analysis import (
    BacktestConfig,
    BacktestFold,
    BacktestResult,
    Metrics,
    RealizedPoint,
)
from cyclescope.domain.errors import InsufficientData

MAX_FOLDS = 20
DIRECTION_ZERO_TOLERANCE = 1e-12


def metrics(
    actual: Sequence[float],
    predicted: Sequence[float],
    actual_returns: Sequence[float],
    predicted_returns: Sequence[float],
) -> Metrics:
    observed = np.asarray(actual, dtype=np.float64)
    modeled = np.asarray(predicted, dtype=np.float64)
    directions = np.asarray(actual_returns, dtype=np.float64)
    predicted_directions = np.asarray(predicted_returns, dtype=np.float64)
    arrays = (observed, modeled, directions, predicted_directions)
    if any(array.ndim != 1 or not len(array) or not np.all(np.isfinite(array)) for array in arrays):
        raise InsufficientData("Metrics require nonempty finite one-dimensional arrays")
    if len(observed) != len(modeled) or len(directions) != len(predicted_directions):
        raise InsufficientData("Metric arrays must have matching denominators")
    error = modeled - observed
    true_sign = np.sign(np.where(np.abs(directions) <= DIRECTION_ZERO_TOLERANCE, 0, directions))
    predicted_sign = np.sign(
        np.where(np.abs(predicted_directions) <= DIRECTION_ZERO_TOLERANCE, 0, predicted_directions)
    )
    return Metrics(
        mae=float(np.mean(np.abs(error))),
        rmse=float(np.sqrt(np.mean(error**2))),
        error_count=len(error),
        directional_accuracy=float(np.mean(true_sign == predicted_sign)),
        direction_count=len(directions),
    )


def walk_forward(series: PriceSeries, config: BacktestConfig) -> BacktestResult:
    series.validate()
    n = len(series.dates)
    horizon = config.horizon_sessions
    step = config.step_sessions or horizon
    boundaries = list(range(config.initial_train_sessions, n - horizon + 1, step))
    if not boundaries:
        raise InsufficientData(
            "Need initial training history followed by a complete forecast horizon"
        )
    if len(boundaries) > MAX_FOLDS:
        raise InsufficientData(
            "At most 20 folds per request; narrow the range or increase step_sessions"
        )
    folds: list[BacktestFold] = []
    actual_logs: list[float] = []
    modeled_logs: list[float] = []
    baseline_logs: list[float] = []
    actual_directions: list[float] = []
    modeled_directions: list[float] = []
    logs = series.log_prices()
    for fold_number, boundary in enumerate(boundaries, 1):
        start = 0 if config.mode == "expanding" else boundary - config.initial_train_sessions
        # Physically pass only training observations to the forecasting implementation.
        training = PriceSeries(series.dates[start:boundary], series.closes[start:boundary])
        prediction = forecast(
            training, training.dates[-1], len(training.dates), horizon, config.model
        )
        actual = logs[boundary : boundary + horizon].tolist()
        predicted = [point.log_value for point in prediction.points]
        baseline = float(logs[boundary - 1])
        baseline_values = [baseline] * horizon
        realized_dates = series.dates[boundary : boundary + horizon]
        if tuple(point.session_date for point in prediction.points) != realized_dates:
            raise InsufficientData("Forecast session dates do not match evaluation targets")
        actual_direction = actual[-1] - baseline
        predicted_direction = predicted[-1] - baseline
        training_hash = hashlib.sha256(
            json.dumps(
                {"dates": [day.isoformat() for day in training.dates], "closes": training.closes},
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        folds.append(
            BacktestFold(
                fold=fold_number,
                train_start=training.dates[0],
                train_end=training.dates[-1],
                test_start=realized_dates[0],
                test_end=realized_dates[-1],
                training_input_hash=training_hash,
                forecast=prediction,
                baseline_log_price=baseline,
                realized=tuple(
                    RealizedPoint(
                        session_offset=i + 1,
                        session_date=day,
                        value=series.closes[boundary + i],
                        log_value=actual[i],
                    )
                    for i, day in enumerate(realized_dates)
                ),
                harmonic_metrics=metrics(
                    actual, predicted, [actual_direction], [predicted_direction]
                ),
                baseline_metrics=metrics(actual, baseline_values, [actual_direction], [0.0]),
            )
        )
        actual_logs.extend(actual)
        modeled_logs.extend(predicted)
        baseline_logs.extend(baseline_values)
        actual_directions.append(actual_direction)
        modeled_directions.append(predicted_direction)
    return BacktestResult(
        config=config,
        start=series.dates[0],
        end=series.dates[-1],
        input_sample_count=n,
        horizon_sessions=horizon,
        fold_count=len(folds),
        evaluated_forecast_count=len(actual_logs),
        unscored_sessions_after_initial_training=n
        - config.initial_train_sessions
        - len(actual_logs),
        folds=tuple(folds),
        harmonic_metrics=metrics(actual_logs, modeled_logs, actual_directions, modeled_directions),
        baseline_metrics=metrics(actual_logs, baseline_logs, actual_directions, [0.0] * len(folds)),
    )
