"""Versioned numerical contracts. All floats must serialize to finite JSON numbers."""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from cyclescope.domain.models import DomainModel

Finite = Annotated[float, Field(allow_inf_nan=False)]


class AnalysisModel(DomainModel):
    model_config = ConfigDict(allow_inf_nan=False)


class FFTConfig(AnalysisModel):
    input: Literal["detrended_log_adjusted_close", "log_returns"] = "detrended_log_adjusted_close"
    detrend: Literal["linear", "constant"] = "linear"
    window: Literal["hann", "boxcar"] = "hann"
    min_period_sessions: Annotated[float, Field(ge=2, le=1260)] = 4
    max_period_sessions: Annotated[float | None, Field(ge=2, le=1260)] = None
    min_repetitions: Annotated[int, Field(ge=2, le=10, strict=True)] = 2
    prominence_ratio: Annotated[float, Field(ge=0, le=1)] = 0.05
    peak_distance_bins: Annotated[int, Field(ge=1, le=50, strict=True)] = 1
    max_peaks: Annotated[int, Field(ge=1, le=5, strict=True)] = 3

    @model_validator(mode="after")
    def ordered_periods(self) -> Self:
        if (
            self.max_period_sessions is not None
            and self.max_period_sessions < self.min_period_sessions
        ):
            raise ValueError("max_period_sessions must be >= min_period_sessions")
        return self


class SpectrumPoint(AnalysisModel):
    frequency: Finite
    period_sessions: Finite
    power: Annotated[float, Field(ge=0)]


class CycleEstimate(SpectrumPoint):
    rank: int
    significance_status: Literal["not_tested"] = "not_tested"


class SpectrumResult(AnalysisModel):
    sample_count: int
    frequency_unit: Literal["cycles_per_trading_session"] = "cycles_per_trading_session"
    period_unit: Literal["trading_sessions"] = "trading_sessions"
    normalization: Literal["one_sided_psd_fs_1"] = "one_sided_psd_fs_1"
    power_unit: Literal["input_units_squared_per_cycles_per_session"] = (
        "input_units_squared_per_cycles_per_session"
    )
    frequency_resolution: Finite
    effective_max_period_sessions: Finite
    cycles: tuple[CycleEstimate, ...]
    spectrum: tuple[SpectrumPoint, ...]
    warnings: tuple[str, ...] = ()


class CycleResult(AnalysisModel):
    as_of: date
    train_start: date
    forecast_origin: date
    price_sample_count: int
    config: FFTConfig
    analysis: SpectrumResult


class HarmonicConfig(AnalysisModel):
    fft: FFTConfig = Field(default_factory=FFTConfig)
    max_harmonics: Annotated[int, Field(ge=1, le=3, strict=True)] = 3
    ridge_alpha: Annotated[float, Field(ge=0, le=1000)] = 0.01
    refine_frequencies: bool = True
    frequency_refinement_max_nfev: Annotated[int, Field(ge=10, le=200, strict=True)] = 100
    bootstrap_draws: Annotated[int, Field(ge=50, le=500, strict=True)] = 100
    bootstrap_block_sessions: Annotated[int, Field(ge=1, le=30, strict=True)] = 5
    seed: Annotated[int, Field(ge=0, le=2**32 - 1, strict=True)] = 0
    residual_quantile_mass: Annotated[float, Field(ge=0.5, le=0.99)] = 0.9
    turn_min_separation_sessions: Annotated[int, Field(ge=1, le=30, strict=True)] = 3
    turn_prominence_log_price: Annotated[float, Field(ge=0, le=1)] = 0.001
    turn_window_tolerance_sessions: Annotated[int, Field(ge=0, le=10, strict=True)] = 2


class FrequencyRefinement(AnalysisModel):
    method: Literal["bounded_variable_projection"] = "bounded_variable_projection"
    status: Literal[
        "refined",
        "disabled",
        "no_cycles",
        "unchanged",
        "fallback_not_converged",
        "fallback_no_improvement",
        "fallback_numerical_failure",
    ]
    frequency_unit: Literal["cycles_per_trading_session"] = "cycles_per_trading_session"
    initial_periods_sessions: tuple[Finite, ...]
    fitted_periods_sessions: tuple[Finite, ...]
    frequency_bounds: tuple[tuple[Finite, Finite], ...]
    objective: Literal["training_squared_log_residuals_plus_ridge_penalty"] = (
        "training_squared_log_residuals_plus_ridge_penalty"
    )
    initial_objective: Annotated[float, Field(ge=0)]
    final_objective: Annotated[float, Field(ge=0)]
    nfev: int
    converged: bool | None


class HarmonicFit(AnalysisModel):
    # v1 remains readable in immutable historical reports; newly fitted models use v2.
    model_version: Literal["harmonic-ridge-log-price-v1", "harmonic-increment-log-price-v2"] = (
        "harmonic-increment-log-price-v2"
    )
    target: Literal["log_adjusted_close"] = "log_adjusted_close"
    periods_sessions: tuple[Finite, ...]
    # Columns: intercept, t/time_scale, cos_1, sin_1, ..., cos_K, sin_K.
    coefficients: tuple[Finite, ...]
    time_scale_sessions: int
    ridge_alpha: Finite
    training_residual_rmse_log_price: Finite
    projection_method: Literal["conditional_fitted_change"] | None = None
    observed_origin_log_price: Finite | None = None
    fitted_origin_log_price: Finite | None = None
    origin_adjustment_log_price: Finite | None = None
    frequency_refinement: FrequencyRefinement | None = None


class ForecastPoint(AnalysisModel):
    session_offset: int
    session_date: date
    value: Annotated[float, Field(gt=0)]
    log_value: Finite
    lower: Annotated[float, Field(gt=0)]
    upper: Annotated[float, Field(gt=0)]


class TurningPoint(AnalysisModel):
    kind: Literal["peak", "trough"]
    session_offset: int
    session_date: date
    window_start_offset: int
    window_end_offset: int
    window_start: date
    window_end: date
    window_method: Literal["heuristic_session_tolerance"] = "heuristic_session_tolerance"


class UncertaintyMethod(AnalysisModel):
    method: Literal[
        "training_residual_circular_block_bootstrap", "training_residual_change_block_bootstrap"
    ] = "training_residual_change_block_bootstrap"
    calibrated: Literal[False] = False
    label: Literal["exploratory_uncalibrated_band"] = "exploratory_uncalibrated_band"
    residual_quantile_mass: Finite
    bootstrap_draws: int
    block_sessions: int
    seed: int
    frequency_selection_uncertainty_included: Literal[False] = False


class ForecastResult(AnalysisModel):
    as_of: date
    forecast_origin: date
    train_start: date
    train_end: date
    training_sample_count: int
    horizon_sessions: int
    last_observed_price: Finite
    price_unit: Literal["USD_per_share"] = "USD_per_share"
    period_unit: Literal["trading_sessions"] = "trading_sessions"
    config: HarmonicConfig
    fit: HarmonicFit
    selected_cycles: tuple[CycleEstimate, ...]
    points: tuple[ForecastPoint, ...]
    turning_points: tuple[TurningPoint, ...]
    uncertainty: UncertaintyMethod
    warnings: tuple[str, ...]


class BacktestConfig(AnalysisModel):
    initial_train_sessions: Annotated[int, Field(ge=32, le=1260, strict=True)] = 360
    horizon_sessions: Annotated[int, Field(ge=1, le=63, strict=True)] = 20
    step_sessions: Annotated[int | None, Field(ge=1, le=2520, strict=True)] = None
    mode: Literal["expanding", "rolling"] = "expanding"
    model: HarmonicConfig = Field(default_factory=HarmonicConfig)

    @model_validator(mode="after")
    def nonoverlapping(self) -> Self:
        if self.step_sessions is not None and self.step_sessions < self.horizon_sessions:
            raise ValueError(
                "step_sessions must be >= horizon_sessions; test windows do not overlap"
            )
        return self


class Metrics(AnalysisModel):
    target: Literal["log_adjusted_close"] = "log_adjusted_close"
    error_unit: Literal["natural_log_price"] = "natural_log_price"
    mae: Annotated[float, Field(ge=0)]
    rmse: Annotated[float, Field(ge=0)]
    error_count: int
    directional_accuracy: Annotated[float, Field(ge=0, le=1)]
    direction_count: int
    direction_definition: Literal["horizon_endpoint_return_sign_including_ties"] = (
        "horizon_endpoint_return_sign_including_ties"
    )
    direction_zero_tolerance_log_price: float = 1e-12


class RealizedPoint(AnalysisModel):
    session_offset: int
    session_date: date
    value: Annotated[float, Field(gt=0)]
    log_value: Finite


class BacktestFold(AnalysisModel):
    fold: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    training_input_hash: str
    forecast: ForecastResult
    realized: tuple[RealizedPoint, ...]
    baseline_name: Literal["random_walk_last_observed_log_price"] = (
        "random_walk_last_observed_log_price"
    )
    baseline_log_price: Finite
    harmonic_metrics: Metrics
    baseline_metrics: Metrics


class BacktestResult(AnalysisModel):
    config: BacktestConfig
    start: date
    end: date
    input_sample_count: int
    horizon_sessions: int
    fold_count: int
    evaluated_forecast_count: int
    unscored_sessions_after_initial_training: int
    aggregation: Literal["pooled_errors_all_offsets_direction_at_horizon_endpoint"] = (
        "pooled_errors_all_offsets_direction_at_horizon_endpoint"
    )
    folds: tuple[BacktestFold, ...]
    harmonic_metrics: Metrics
    baseline_metrics: Metrics
    warnings: tuple[str, ...] = (
        "retrospective_evaluation_on_recorded_adjusted_snapshot",
        "no_trading_profit_or_significance_claim",
        "uncertainty_coverage_not_evaluated",
    )
