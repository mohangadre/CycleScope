"""Stored coverage and explicit, bounded market-data downloads; no order execution."""

from datetime import UTC, datetime
from threading import BoundedSemaphore

from fastapi import APIRouter, HTTPException
from sqlalchemy import Engine

from cyclescope.domain.calendar import completed_session_before_today, session_dates
from cyclescope.domain.errors import AnalysisBusy, InsufficientData
from cyclescope.domain.models import DateRange, Symbol
from cyclescope.domain.views import PriceCoverageResponse, PriceRefreshResponse
from cyclescope.providers.base import MarketDataProvider, instrument_for
from cyclescope.services.ingestion import ingest
from cyclescope.services.prices import read_coverage


def market_data_router(
    engine: Engine, provider: MarketDataProvider, slots: BoundedSemaphore
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/prices")

    @router.get("/{ticker}/coverage", response_model=PriceCoverageResponse)
    def coverage(ticker: Symbol) -> PriceCoverageResponse:
        return read_coverage(engine, provider, ticker)

    @router.post("/{ticker}/refresh", response_model=PriceRefreshResponse)
    def refresh(ticker: Symbol, period: DateRange) -> PriceRefreshResponse:
        instrument_for(ticker)
        if provider.data_kind != "real":
            raise HTTPException(422, "Market downloads require the configured real Alpaca provider")
        dates = session_dates(period)
        if not dates:
            raise InsufficientData("Choose a range containing at least one exchange session")
        latest = completed_session_before_today(datetime.now(UTC))
        if dates[-1] > latest:
            raise InsufficientData(
                f"Completed daily prices are available only through {latest}; change the end date"
            )
        if not slots.acquire(blocking=False):
            raise AnalysisBusy(
                "Data/analysis capacity is busy; retry after an active request completes"
            )
        try:
            run_id = ingest(engine, provider, ticker, period)
            return PriceRefreshResponse(
                ticker=ticker,
                provider=provider.provider_id,
                requested_range=period,
                ingestion_run_id=run_id,
                coverage=read_coverage(engine, provider, ticker),
            )
        finally:
            slots.release()

    return router
