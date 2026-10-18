"""Orchestrate pure analysis and snapshot persistence; no provider network requests."""

import hashlib
import importlib.metadata
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine

from cyclescope.analytics.backtesting import walk_forward
from cyclescope.analytics.fourier import analyze_cycles
from cyclescope.analytics.harmonic import forecast
from cyclescope.analytics.series import PriceSeries
from cyclescope.domain.analysis import BacktestResult, CycleResult, ForecastResult
from cyclescope.domain.errors import AnalysisNotFound, ReplayMismatch
from cyclescope.domain.experiments import (
    AnalysisKind,
    AnalysisResponse,
    BacktestRequest,
    CycleRequest,
    DataProvenance,
    ForecastRequest,
    InputSnapshot,
    SoftwareIdentity,
)
from cyclescope.providers.base import MarketDataProvider
from cyclescope.storage.analysis import load_raw_run, load_snapshot, store_run


def software_identity() -> SoftwareIdentity:
    source = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for file in sorted(source.rglob("*.py")):
        digest.update(file.relative_to(source).as_posix().encode())
        digest.update(b"\0")
        digest.update(file.read_bytes())
    revision = None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=2, check=False
        )
        if result.returncode == 0 and re.fullmatch(r"[a-f0-9]{40}", result.stdout.strip()):
            revision = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # Installed containers need not contain Git; source hash is authoritative.
    versions = {
        name: importlib.metadata.version(name)
        for name in ("numpy", "scipy", "exchange-calendars", "cyclescope")
    }
    versions["python"] = sys.version.split()[0]
    return SoftwareIdentity(
        code_sha256=digest.hexdigest(), git_revision=revision, libraries=versions
    )


def compute(
    snapshot: InputSnapshot, request: CycleRequest | ForecastRequest | BacktestRequest
) -> CycleResult | ForecastResult | BacktestResult:
    series = PriceSeries(snapshot.dates, tuple(float(value) for value in snapshot.closes))
    if isinstance(request, CycleRequest):
        return analyze_cycles(series, request.as_of, request.lookback, request.fft)
    if isinstance(request, ForecastRequest):
        return forecast(
            series, request.as_of, request.lookback, request.horizon_sessions, request.model
        )
    return walk_forward(series, request.evaluation)


def run_analysis(
    engine: Engine,
    provider: MarketDataProvider,
    ticker: str,
    request: CycleRequest | ForecastRequest | BacktestRequest,
) -> AnalysisResponse:
    kind: AnalysisKind
    if isinstance(request, BacktestRequest):
        kind = "backtest"
        snapshot = load_snapshot(engine, provider, ticker, start=request.start, end=request.end)
    else:
        kind = "cycles" if isinstance(request, CycleRequest) else "forecast"
        snapshot = load_snapshot(
            engine, provider, ticker, end=request.as_of, lookback=request.lookback
        )
    result = compute(snapshot, request)
    response = AnalysisResponse(
        run_id=uuid4(),
        created_at=datetime.now(UTC),
        kind=kind,
        source=DataProvenance(
            ticker=snapshot.ticker,
            provider=snapshot.provider,
            data_kind=snapshot.data_kind,
            adjustment_basis=snapshot.adjustment_basis,
            input_hash=snapshot.content_hash(),
            sample_count=len(snapshot.dates),
            data_versions=snapshot.data_versions,
            ingestion_run_ids=snapshot.ingestion_run_ids,
        ),
        software=software_identity(),
        result=result,
    )
    store_run(engine, response, snapshot, request.model_dump(mode="json"))
    return response


def get_backtest(engine: Engine, run_id: UUID) -> dict[str, Any]:
    response, _, _ = load_raw_run(engine, run_id)
    if response.get("kind") != "backtest":
        raise AnalysisNotFound("This run ID does not identify a backtest")
    return response


def replay_backtest(engine: Engine, run_id: UUID) -> AnalysisResponse:
    raw, raw_snapshot, config = load_raw_run(engine, run_id)
    if raw.get("kind") != "backtest":
        raise AnalysisNotFound("This run ID does not identify a backtest")
    # Check version identity before parsing. New configuration defaults must never
    # change the interpretation of a report produced by an older implementation.
    if raw.get("schema_version") != "analysis-v2":
        raise ReplayMismatch(
            "Saved model/schema version differs; retrieve the original report instead"
        )
    identity = software_identity()
    saved_identity = raw.get("software", {})
    if identity.code_sha256 != saved_identity.get(
        "code_sha256"
    ) or identity.libraries != saved_identity.get("libraries"):
        raise ReplayMismatch(
            "Saved code/library versions differ; retrieve the original report instead"
        )
    response = AnalysisResponse.model_validate(raw)
    snapshot = InputSnapshot.model_validate(raw_snapshot)
    if snapshot.content_hash() != response.source.input_hash:
        raise ReplayMismatch("Saved snapshot integrity check failed")
    result = compute(snapshot, BacktestRequest.model_validate(config))
    if result != response.result:
        raise ReplayMismatch("Recomputed output differs from the saved report")
    return response.model_copy(update={"result": result})
