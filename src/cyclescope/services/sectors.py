"""Orchestrate observed sector calculations and immutable snapshot persistence."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine

from cyclescope.analytics.sectors import rotation
from cyclescope.analytics.series import PriceSeries
from cyclescope.domain.errors import ReplayMismatch
from cyclescope.domain.sectors import SectorInput, SectorRequest, SectorResponse, SectorResult
from cyclescope.providers.base import MarketDataProvider
from cyclescope.services.analysis import software_identity
from cyclescope.storage.sectors import load_sector_input, load_sector_run, store_sector_run


def compute_sector(snapshot: SectorInput, config: SectorRequest) -> SectorResult:
    return rotation(
        {
            symbol: PriceSeries(snapshot.dates, tuple(float(x) for x in values))
            for symbol, values in snapshot.closes.items()
        },
        config,
    )


def run_sector(
    engine: Engine, provider: MarketDataProvider, config: SectorRequest
) -> SectorResponse:
    snapshot = load_sector_input(engine, provider, config)
    result = compute_sector(snapshot, config)
    response = SectorResponse(
        run_id=uuid4(),
        created_at=datetime.now(UTC),
        provider=snapshot.provider,
        data_kind=snapshot.data_kind,
        input_hash=snapshot.content_hash(),
        data_versions=snapshot.data_versions,
        ingestion_run_ids=snapshot.ingestion_run_ids,
        software=software_identity(),
        result=result,
    )
    store_sector_run(engine, response, snapshot)
    return response


def replay_sector(engine: Engine, run_id: UUID) -> SectorResponse:
    raw, saved_input = load_sector_run(engine, run_id)
    identity = software_identity()
    if (
        raw.get("schema_version") != "sectors-v1"
        or raw.get("software", {}).get("code_sha256") != identity.code_sha256
        or raw.get("software", {}).get("libraries") != identity.libraries
    ):
        raise ReplayMismatch(
            "Saved sector code/library versions differ; retrieve the original report"
        )
    response = SectorResponse.model_validate(raw)
    snapshot = SectorInput.model_validate(saved_input)
    if snapshot.content_hash() != response.input_hash:
        raise ReplayMismatch("Saved sector snapshot integrity check failed")
    if compute_sector(snapshot, response.result.config) != response.result:
        raise ReplayMismatch("Recomputed sector output differs from the saved report")
    return response
