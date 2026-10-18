"""Observed, cutoff-isolated sector ratios; no provider I/O or forecast model."""

import numpy as np
from numpy.typing import NDArray

from cyclescope.analytics.series import PriceSeries
from cyclescope.domain.errors import InsufficientData
from cyclescope.domain.models import SECTOR_CATALOG
from cyclescope.domain.sectors import (
    Quadrant,
    SectorPoint,
    SectorRequest,
    SectorResult,
    SectorSeries,
)

BOUNDARY_TOLERANCE_LOG = 1e-12


def classify(log_strength: float, momentum: float) -> Quadrant:
    if not np.isfinite(log_strength) or not np.isfinite(momentum):
        raise InsufficientData("Quadrants require finite values")
    if abs(log_strength) <= BOUNDARY_TOLERANCE_LOG or abs(momentum) <= BOUNDARY_TOLERANCE_LOG:
        return "neutral"
    if log_strength > 0:
        return "leading" if momentum > 0 else "weakening"
    return "improving" if momentum > 0 else "lagging"


def exponentiate(values: NDArray[np.float64]) -> NDArray[np.float64]:
    try:
        with np.errstate(over="raise", invalid="raise", under="raise"):
            result = np.exp(values)
    except FloatingPointError as exc:
        raise InsufficientData("Relative strength is numerically unstable") from exc
    if not np.all(np.isfinite(result)) or np.any(result <= 0):
        raise InsufficientData("Relative strength must be positive and finite")
    return result


def rotation(panel: dict[str, PriceSeries], config: SectorRequest) -> SectorResult:
    expected = {"SPY", *(item.symbol for item in SECTOR_CATALOG)}
    if set(panel) != expected:
        raise InsufficientData("Require SPY and all eight configured sector ETFs")
    # Select before validating, taking logs, smoothing, or computing momentum.
    training = {
        symbol: series.through(config.as_of, config.required_sessions)
        for symbol, series in panel.items()
    }
    benchmark = training["SPY"]
    if any(series.dates != benchmark.dates for series in training.values()):
        raise InsufficientData("Sector and benchmark trading sessions must match exactly")
    benchmark_logs = benchmark.log_prices()
    n = config.required_sessions
    first = n - config.lookback_sessions
    result: list[SectorSeries] = []
    for instrument in SECTOR_CATALOG:
        log_rs = training[instrument.symbol].log_prices() - benchmark_logs
        # Windows are backward-only, including the current session.
        smooth = np.convolve(
            log_rs, np.ones(config.smoothing_sessions) / config.smoothing_sessions, mode="valid"
        )
        offset = config.smoothing_sessions - 1
        indices = np.arange(first, n)
        z = smooth[indices - offset]
        base = float(smooth[first - offset])
        displacement = z - base
        momentum = z - smooth[indices - offset - config.momentum_sessions]
        raw = exponentiate(log_rs[indices])
        normalized = 100 * exponentiate(log_rs[indices] - log_rs[first])
        smoothed = 100 * exponentiate(displacement)
        relative_change = 100 * np.expm1(momentum)
        if any(not np.all(np.isfinite(x)) for x in (normalized, smoothed, relative_change)):
            raise InsufficientData("Normalized relative strength is numerically unstable")
        result.append(
            SectorSeries(
                ticker=instrument.symbol,
                name=instrument.display_name,
                points=tuple(
                    SectorPoint(
                        session_date=benchmark.dates[j],
                        relative_strength=float(raw[i]),
                        normalized_rs=float(normalized[i]),
                        smoothed_normalized_rs=float(smoothed[i]),
                        momentum_log_rs=float(momentum[i]),
                        relative_change_percent=float(relative_change[i]),
                        quadrant=classify(float(displacement[i]), float(momentum[i])),
                    )
                    for i, j in enumerate(indices)
                ),
            )
        )
    return SectorResult(
        as_of=config.as_of,
        observed_through=benchmark.dates[-1],
        normalization_session=benchmark.dates[first],
        input_start=benchmark.dates[0],
        input_sample_count_per_symbol=n,
        config=config,
        sectors=tuple(result),
    )
