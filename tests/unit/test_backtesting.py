from datetime import date

import numpy as np
import pytest
from pydantic import ValidationError

from cyclescope.analytics.backtesting import metrics, walk_forward
from cyclescope.analytics.series import PriceSeries
from cyclescope.domain.analysis import BacktestConfig, HarmonicConfig
from cyclescope.domain.calendar import session_dates
from cyclescope.domain.errors import InsufficientData
from cyclescope.domain.models import DateRange


def data(n: int = 240) -> PriceSeries:
    dates = session_dates(DateRange(start=date(2020, 1, 2), end=date(2024, 12, 31)))[:n]
    t = np.arange(n)
    prices = np.exp(4 + 0.0001 * t + 0.04 * np.sin(2 * np.pi * t / 40))
    return PriceSeries(dates, tuple(prices.tolist()))


@pytest.mark.parametrize("mode", ["expanding", "rolling"])
def test_ordered_nonoverlapping_folds_matching_baseline_and_denominators(mode: str) -> None:
    series = data()
    result = walk_forward(
        series, BacktestConfig(initial_train_sessions=120, horizon_sessions=20, mode=mode)
    )
    assert result.fold_count == 6
    assert result.evaluated_forecast_count == 120
    assert result.harmonic_metrics.error_count == result.baseline_metrics.error_count == 120
    assert result.harmonic_metrics.direction_count == result.baseline_metrics.direction_count == 6
    for i, fold in enumerate(result.folds):
        assert fold.train_end < fold.test_start <= fold.test_end
        assert fold.forecast.forecast_origin == fold.train_end
        assert fold.harmonic_metrics.error_count == fold.baseline_metrics.error_count == 20
        expected_training = 120 + 20 * i if mode == "expanding" else 120
        assert fold.forecast.training_sample_count == expected_training
        assert fold.baseline_log_price == pytest.approx(np.log(series.closes[119 + 20 * i]))
        assert [point.session_date for point in fold.realized] == [
            point.session_date for point in fold.forecast.points
        ]
        if i:
            assert result.folds[i - 1].test_end < fold.test_start
    assert result.unscored_sessions_after_initial_training == 0


def test_no_full_dataset_preprocessing_or_selection_before_split() -> None:
    original = data()
    modified = PriceSeries(
        original.dates, original.closes[:120] + tuple(value * 2 for value in original.closes[120:])
    )
    config = BacktestConfig(initial_train_sessions=120)
    a, b = walk_forward(original, config), walk_forward(modified, config)
    assert a.folds[0].training_input_hash == b.folds[0].training_input_hash
    assert a.folds[0].forecast == b.folds[0].forecast
    assert a.folds[0].realized != b.folds[0].realized
    assert a.folds[0].harmonic_metrics != b.folds[0].harmonic_metrics


def test_metric_formulas_and_zero_direction_rule() -> None:
    result = metrics([0, 1, 2], [0, 2, 4], [1, -1, 0], [2, 1, 0])
    assert result.mae == 1
    assert result.rmse == pytest.approx(np.sqrt(5 / 3))
    assert result.directional_accuracy == 2 / 3
    assert result.error_count == result.direction_count == 3
    flat = metrics([4, 4], [4, 4], [0], [1e-14])
    assert flat.directional_accuracy == 1


@pytest.mark.parametrize(
    "arrays",
    [([], [], [], []), ([1], [1, 2], [0], [0]), ([1], [1], [], [0]), ([np.nan], [1], [0], [0])],
)
def test_invalid_metric_denominators(arrays: tuple[list[float], ...]) -> None:
    with pytest.raises(InsufficientData):
        metrics(*arrays)


def test_step_gaps_and_partial_tail_are_disclosed() -> None:
    result = walk_forward(
        data(245), BacktestConfig(initial_train_sessions=120, horizon_sessions=20, step_sessions=30)
    )
    assert result.fold_count == 4
    assert result.evaluated_forecast_count == 80
    assert result.unscored_sessions_after_initial_training == 45


def test_deterministic_bootstrap_seed_and_json() -> None:
    config = BacktestConfig(initial_train_sessions=120, model=HarmonicConfig(seed=123))
    result = walk_forward(data(), config)
    assert result.model_dump_json() == walk_forward(data(), config).model_dump_json()


def test_insufficient_history_and_workload_bounds() -> None:
    with pytest.raises(InsufficientData, match="complete forecast horizon"):
        walk_forward(data(130), BacktestConfig(initial_train_sessions=120))
    with pytest.raises(InsufficientData, match="At most 20 folds"):
        walk_forward(data(240), BacktestConfig(initial_train_sessions=32, horizon_sessions=1))
    with pytest.raises(ValidationError, match="overlap"):
        BacktestConfig(horizon_sessions=20, step_sessions=10)
