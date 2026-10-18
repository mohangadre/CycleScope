from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from threading import BoundedSemaphore
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import Engine

from cyclescope.domain.analysis import FFTConfig
from cyclescope.domain.errors import AnalysisBusy
from cyclescope.domain.experiments import (
    AnalysisResponse,
    BacktestRequest,
    CycleRequest,
    ForecastRequest,
)
from cyclescope.domain.models import Symbol
from cyclescope.providers.base import MarketDataProvider
from cyclescope.services.analysis import get_backtest, replay_backtest, run_analysis
from cyclescope.storage.analysis import load_raw_run


def analysis_router(
    engine: Engine, provider: MarketDataProvider, slots: BoundedSemaphore
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @contextmanager
    def capacity() -> Iterator[None]:
        if not slots.acquire(blocking=False):
            raise AnalysisBusy("Analysis capacity is busy; retry after an active request completes")
        try:
            yield
        finally:
            slots.release()

    @router.get("/cycles/{ticker}", response_model=AnalysisResponse)
    def cycles(
        ticker: Symbol,
        as_of: date,
        lookback: Annotated[int, Query(ge=32, le=2520)] = 504,
        input: Literal[
            "detrended_log_adjusted_close", "log_returns"
        ] = "detrended_log_adjusted_close",
        detrend: Literal["linear", "constant"] = "linear",
        window: Literal["hann", "boxcar"] = "hann",
        min_period_sessions: Annotated[float, Query(ge=2, le=1260)] = 4,
        max_period_sessions: Annotated[float | None, Query(ge=2, le=1260)] = None,
        min_repetitions: Annotated[int, Query(ge=2, le=10)] = 2,
        prominence_ratio: Annotated[float, Query(ge=0, le=1)] = 0.05,
        peak_distance_bins: Annotated[int, Query(ge=1, le=50)] = 1,
        max_peaks: Annotated[int, Query(ge=1, le=5)] = 3,
    ) -> AnalysisResponse:
        try:
            request = CycleRequest(
                as_of=as_of,
                lookback=lookback,
                fft=FFTConfig(
                    input=input,
                    detrend=detrend,
                    window=window,
                    min_period_sessions=min_period_sessions,
                    max_period_sessions=max_period_sessions,
                    min_repetitions=min_repetitions,
                    prominence_ratio=prominence_ratio,
                    peak_distance_bins=peak_distance_bins,
                    max_peaks=max_peaks,
                ),
            )
        except ValidationError as exc:
            raise HTTPException(422, "Invalid or inconsistent FFT configuration") from exc
        with capacity():
            return run_analysis(engine, provider, ticker, request)

    @router.post("/forecasts/{ticker}", response_model=AnalysisResponse)
    def forecasts(ticker: Symbol, request: ForecastRequest) -> AnalysisResponse:
        with capacity():
            return run_analysis(engine, provider, ticker, request)

    @router.post("/backtests", response_model=AnalysisResponse)
    def backtests(request: BacktestRequest) -> AnalysisResponse:
        with capacity():
            return run_analysis(engine, provider, request.ticker, request)

    @router.get("/backtests/{run_id}", response_model=AnalysisResponse)
    def saved_backtest(run_id: UUID) -> JSONResponse:
        return JSONResponse(content=get_backtest(engine, run_id))

    @router.post("/backtests/{run_id}/replay", response_model=AnalysisResponse)
    def replay(run_id: UUID) -> AnalysisResponse:
        with capacity():
            return replay_backtest(engine, run_id)

    @router.get("/analyses/{run_id}", response_model=AnalysisResponse)
    def saved_analysis(run_id: UUID) -> JSONResponse:
        return JSONResponse(content=load_raw_run(engine, run_id)[0])

    return router
