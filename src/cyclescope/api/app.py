import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date
from threading import BoundedSemaphore
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from cyclescope.api.analysis import analysis_router
from cyclescope.api.limits import AnalysisBodyLimit
from cyclescope.api.sectors import sector_router
from cyclescope.config import Settings
from cyclescope.domain.errors import CycleScopeError
from cyclescope.domain.models import DateRange, Symbol
from cyclescope.domain.views import ErrorResponse, HealthResponse, PricesResponse, SymbolsResponse
from cyclescope.providers.base import MarketDataProvider, instruments_for
from cyclescope.providers.factory import make_provider
from cyclescope.services.prices import read_prices
from cyclescope.storage.database import make_engine

logger = logging.getLogger("cyclescope.requests")
SCHEMA_REVISION = "0003"


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    provider: MarketDataProvider | None = None,
) -> FastAPI:
    config = settings or Settings()
    db = engine if engine is not None else make_engine(config.database_url.get_secret_value())
    source = provider if provider is not None else make_provider(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        if engine is None:
            db.dispose()

    app = FastAPI(
        title="CycleScope",
        version="0.4.0",
        description=(
            "Data, FFT, exploratory harmonic forecasts and walk-forward evaluation. "
            "Sources and uncalibrated uncertainty are explicit."
        ),
        lifespan=lifespan,
        responses={code: {"model": ErrorResponse} for code in (404, 409, 413, 422, 500, 502, 503)},
    )
    app.state.analysis_slots = BoundedSemaphore(2)
    app.include_router(analysis_router(db, source, app.state.analysis_slots))
    app.include_router(sector_router(db, source, app.state.analysis_slots))
    app.add_middleware(AnalysisBodyLimit)

    @app.middleware("http")
    async def request_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        started = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        logger.info(
            json.dumps(
                {
                    "request_id": request.state.request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                }
            )
        )
        return response

    def error(request: Request, code: str, message: str, status: int) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            headers={"X-Request-ID": getattr(request.state, "request_id", "unassigned")},
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": getattr(request.state, "request_id", "unassigned"),
                }
            },
        )

    @app.exception_handler(CycleScopeError)
    async def domain_error(request: Request, exc: CycleScopeError) -> JSONResponse:
        return error(request, exc.code, str(exc), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Return validation messages, never raw request values or Pydantic contexts.
        fields = sorted({".".join(str(part) for part in item["loc"]) for item in exc.errors()})
        return error(request, "invalid_request", "Invalid fields: " + ", ".join(fields), 422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return error(request, "database_unavailable", "Database operation unavailable", 503)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error(request, "http_error", str(exc.detail), exc.status_code)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        return error(request, "internal_error", "An internal error occurred", 500)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
    def health() -> HealthResponse | JSONResponse:
        try:
            with db.connect() as connection:
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
                connection.execute(text("SELECT symbol FROM daily_bars LIMIT 1"))
                if revision != SCHEMA_REVISION:
                    raise HTTPException(status_code=503)
        except (SQLAlchemyError, HTTPException):
            return JSONResponse(
                status_code=503,
                content=HealthResponse(
                    status="unavailable",
                    database="unavailable",
                    provider=source.provider_id,
                    data_kind=source.data_kind,
                ).model_dump(),
            )
        return HealthResponse(
            status="ok", database="ready", provider=source.provider_id, data_kind=source.data_kind
        )

    @app.get("/api/v1/symbols", response_model=SymbolsResponse)
    def symbols() -> SymbolsResponse:
        return SymbolsResponse(
            provider=source.provider_id,
            data_kind=source.data_kind,
            instruments=instruments_for(source),
        )

    @app.get("/api/v1/prices/{ticker}", response_model=PricesResponse)
    def prices(
        ticker: Symbol,
        start: date,
        end: date,
        limit: Annotated[int, Query(ge=1, le=1000)] = 500,
        offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    ) -> PricesResponse:
        try:
            period = DateRange(start=start, end=end)
        except ValueError as exc:
            raise HTTPException(
                422, "Invalid date range; require start <= end within 3660 days, 1990–2035"
            ) from exc
        return read_prices(db, source, ticker, period, limit, offset)

    return app
