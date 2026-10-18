from datetime import date
from threading import BoundedSemaphore
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from cyclescope.domain.errors import AnalysisBusy
from cyclescope.domain.sectors import SectorRequest, SectorResponse
from cyclescope.providers.base import MarketDataProvider
from cyclescope.services.sectors import replay_sector, run_sector
from cyclescope.storage.sectors import load_sector_run


def sector_router(
    engine: Engine, provider: MarketDataProvider, slots: BoundedSemaphore
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/sectors")

    @router.get("/rotation", response_model=SectorResponse)
    def sectors(
        as_of: Annotated[date, Query(ge=date(1990, 1, 1), le=date(2035, 12, 31))],
        lookback_sessions: Annotated[int, Query(ge=32, le=1260)] = 126,
        momentum_sessions: Annotated[int, Query(ge=1, le=126)] = 20,
        smoothing_sessions: Annotated[int, Query(ge=1, le=30)] = 5,
    ) -> SectorResponse:
        if not slots.acquire(blocking=False):
            raise AnalysisBusy("Analysis capacity is busy; retry after an active request completes")
        try:
            return run_sector(
                engine,
                provider,
                SectorRequest(
                    as_of=as_of,
                    lookback_sessions=lookback_sessions,
                    momentum_sessions=momentum_sessions,
                    smoothing_sessions=smoothing_sessions,
                ),
            )
        finally:
            slots.release()

    @router.get("/runs/{run_id}", response_model=SectorResponse)
    def saved(run_id: UUID) -> JSONResponse:
        return JSONResponse(content=load_sector_run(engine, run_id)[0])

    @router.post("/runs/{run_id}/replay", response_model=SectorResponse)
    def replay(run_id: UUID) -> SectorResponse:
        if not slots.acquire(blocking=False):
            raise AnalysisBusy("Analysis capacity is busy; retry after an active request completes")
        try:
            return replay_sector(engine, run_id)
        finally:
            slots.release()

    return router
