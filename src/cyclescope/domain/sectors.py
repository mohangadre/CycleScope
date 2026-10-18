"""Versioned, observed sector-relative strength contracts and retained inputs."""

import hashlib
import json
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from cyclescope.domain.analysis import AnalysisModel, Finite
from cyclescope.domain.experiments import SoftwareIdentity
from cyclescope.domain.models import DataKind, Price, Symbol

Quadrant = Literal["leading", "improving", "weakening", "lagging", "neutral"]


class SectorRequest(AnalysisModel):
    as_of: Annotated[date, Field(ge=date(1990, 1, 1), le=date(2035, 12, 31))]
    lookback_sessions: Annotated[int, Field(ge=32, le=1260, strict=True)] = 126
    momentum_sessions: Annotated[int, Field(ge=1, le=126, strict=True)] = 20
    smoothing_sessions: Annotated[int, Field(ge=1, le=30, strict=True)] = 5

    @property
    def required_sessions(self) -> int:
        return self.lookback_sessions + self.momentum_sessions + self.smoothing_sessions - 1


class SectorInput(AnalysisModel):
    provider: str
    data_kind: DataKind
    adjustment_basis: Literal["split_dividend_adjusted"] = "split_dividend_adjusted"
    currency: Literal["USD"] = "USD"
    dates: tuple[date, ...]
    closes: dict[Symbol, tuple[Price, ...]]
    data_versions: dict[Symbol, tuple[str, ...]]
    ingestion_run_ids: dict[Symbol, tuple[UUID, ...]]

    def content_hash(self) -> str:
        content = self.model_dump(mode="json", exclude={"ingestion_run_ids"})
        return hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()


class SectorPoint(AnalysisModel):
    session_date: date
    relative_strength: Annotated[float, Field(gt=0)]
    normalized_rs: Annotated[float, Field(gt=0)]
    smoothed_normalized_rs: Annotated[float, Field(gt=0)]
    momentum_log_rs: Finite
    relative_change_percent: Finite
    quadrant: Quadrant


class SectorSeries(AnalysisModel):
    ticker: Symbol
    name: str
    points: tuple[SectorPoint, ...]


class SectorResult(AnalysisModel):
    model_version: Literal["sector-relative-strength-v1"] = "sector-relative-strength-v1"
    observation_kind: Literal["observed_relative_performance"] = "observed_relative_performance"
    benchmark: Literal["SPY"] = "SPY"
    as_of: date
    observed_through: date
    normalization_session: date
    input_start: date
    input_sample_count_per_symbol: int
    config: SectorRequest
    smoothing_method: Literal["trailing_mean_log_price_ratio"] = "trailing_mean_log_price_ratio"
    raw_normalization: Literal["100_times_RS_over_reference_RS"] = "100_times_RS_over_reference_RS"
    smoothed_normalization: Literal["100_times_exp_smoothed_log_RS_minus_reference"] = (
        "100_times_exp_smoothed_log_RS_minus_reference"
    )
    momentum_unit: Literal["natural_log_relative_strength_change"] = (
        "natural_log_relative_strength_change"
    )
    period_unit: Literal["trading_sessions"] = "trading_sessions"
    strength_axis: float = 100
    momentum_axis: float = 0
    boundary_tolerance_log: float = 1e-12
    boundary_policy: Literal["neutral_on_either_axis"] = "neutral_on_either_axis"
    sectors: tuple[SectorSeries, ...]
    warnings: tuple[str, ...] = (
        "descriptive_quadrants_not_predictions_or_investment_advice",
        "recorded_adjusted_snapshots_not_point_in_time_guaranteed",
        "normalization_reference_changes_with_lookback",
        "strict_complete_matching_sessions_no_interpolation",
    )


class SectorResponse(AnalysisModel):
    schema_version: Literal["sectors-v1"] = "sectors-v1"
    run_id: UUID
    created_at: datetime
    provider: str
    data_kind: DataKind
    adjustment_basis: Literal["split_dividend_adjusted"] = "split_dividend_adjusted"
    currency: Literal["USD"] = "USD"
    input_hash: str
    data_versions: dict[Symbol, tuple[str, ...]]
    ingestion_run_ids: dict[Symbol, tuple[UUID, ...]]
    software: SoftwareIdentity
    result: SectorResult
