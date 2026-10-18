"""Transport-neutral requests and immutable experiment/snapshot result envelopes."""

import hashlib
import json
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from cyclescope.domain.analysis import (
    AnalysisModel,
    BacktestConfig,
    BacktestResult,
    CycleResult,
    FFTConfig,
    ForecastResult,
    HarmonicConfig,
)
from cyclescope.domain.models import AdjustmentBasis, DataKind, DateRange, Price, Symbol

AnalysisKind = Literal["cycles", "forecast", "backtest"]


class CycleRequest(AnalysisModel):
    as_of: Annotated[date, Field(ge=date(1990, 1, 1), le=date(2035, 12, 31))]
    lookback: Annotated[int, Field(ge=32, le=2520, strict=True)] = 504
    fft: FFTConfig = Field(default_factory=FFTConfig)


class ForecastRequest(AnalysisModel):
    as_of: Annotated[date, Field(ge=date(1990, 1, 1), le=date(2035, 12, 31))]
    lookback: Annotated[int, Field(ge=32, le=2520, strict=True)] = 504
    horizon_sessions: Annotated[int, Field(ge=1, le=126, strict=True)] = 20
    model: HarmonicConfig = Field(default_factory=HarmonicConfig)


class BacktestRequest(DateRange):
    ticker: Symbol
    evaluation: BacktestConfig = Field(default_factory=BacktestConfig)


class InputSnapshot(AnalysisModel):
    ticker: Symbol
    provider: str
    data_kind: DataKind
    adjustment_basis: AdjustmentBasis = "split_dividend_adjusted"
    currency: Literal["USD"] = "USD"
    data_versions: tuple[str, ...]
    ingestion_run_ids: tuple[UUID, ...]
    dates: tuple[date, ...]
    closes: tuple[Price, ...]

    def content_hash(self) -> str:
        # Audit run IDs can change on a value-identical re-ingestion. Numerical
        # input identity depends on values/source, never on later/future bars.
        content = self.model_dump(mode="json", exclude={"ingestion_run_ids"})
        return hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()


class DataProvenance(AnalysisModel):
    ticker: Symbol
    provider: str
    data_kind: DataKind
    adjustment_basis: AdjustmentBasis
    input_hash: str
    sample_count: int
    data_versions: tuple[str, ...]
    ingestion_run_ids: tuple[UUID, ...]
    availability_policy: Literal["recorded_adjusted_snapshot_not_point_in_time_feed"] = (
        "recorded_adjusted_snapshot_not_point_in_time_feed"
    )


class SoftwareIdentity(AnalysisModel):
    code_sha256: str
    git_revision: str | None
    libraries: dict[str, str]


class AnalysisResponse(AnalysisModel):
    schema_version: Literal["analysis-v1", "analysis-v2"] = "analysis-v2"
    run_id: UUID
    created_at: datetime
    kind: AnalysisKind
    source: DataProvenance
    software: SoftwareIdentity
    result: CycleResult | ForecastResult | BacktestResult
