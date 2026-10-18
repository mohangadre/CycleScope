"""One-sided, fs=1 session periodogram; spectral prominence is not significance."""

from collections.abc import Sequence
from datetime import date

import numpy as np
from scipy.signal import detrend, find_peaks, get_window

from cyclescope.analytics.series import MAX_SAMPLES, MIN_SAMPLES, PriceSeries
from cyclescope.domain.analysis import (
    CycleEstimate,
    CycleResult,
    FFTConfig,
    SpectrumPoint,
    SpectrumResult,
)
from cyclescope.domain.errors import InsufficientData


def periodogram(values: Sequence[float], config: FFTConfig) -> SpectrumResult:
    """Transform an already-chosen training signal, using no external data/state."""
    raw = np.asarray(values, dtype=np.float64)
    n = len(raw)
    if raw.ndim != 1 or not MIN_SAMPLES <= n <= MAX_SAMPLES or not np.all(np.isfinite(raw)):
        raise InsufficientData(f"FFT requires {MIN_SAMPLES}–{MAX_SAMPLES} finite scalar samples")
    upper = min(config.max_period_sessions or float(n), n / config.min_repetitions)
    if config.min_period_sessions > upper:
        raise InsufficientData("History is too short for the requested period/repetition bounds")
    centered = np.asarray(detrend(raw, type=config.detrend), dtype=np.float64)
    # Numerical roundoff in a constant or exactly linear series is not a cycle.
    floor = 64 * np.finfo(np.float64).eps * max(1.0, float(np.max(np.abs(raw))))
    degenerate = float(np.max(np.abs(centered))) <= floor
    if degenerate:
        centered = np.zeros_like(centered)
    window = np.asarray(get_window(config.window, n, fftbins=True), dtype=np.float64)
    transformed = np.fft.rfft(centered * window)
    powers = np.abs(transformed) ** 2 / float(np.sum(window**2))
    powers[1 : -1 if n % 2 == 0 else None] *= 2
    frequencies = np.fft.rfftfreq(n, d=1.0)
    eligible = (
        (frequencies > 0)
        & (frequencies >= 1 / upper)
        & (frequencies <= 1 / config.min_period_sessions)
    )
    indices = np.flatnonzero(eligible)
    if not len(indices):
        raise InsufficientData("No Fourier bins fall within the requested period bounds")
    threshold = config.prominence_ratio * float(np.max(powers[indices]))
    # Pad to include a genuine Nyquist maximum; DC is never eligible.
    candidate_indices, _ = find_peaks(
        np.r_[-np.inf, powers[1:], -np.inf],
        prominence=threshold,
        distance=config.peak_distance_bins,
    )
    candidates = [int(k) for k in candidate_indices if k in indices and powers[k] > 0]
    ranked = sorted(candidates, key=lambda k: (-float(powers[k]), float(frequencies[k])))
    cycles = tuple(
        CycleEstimate(
            rank=rank,
            frequency=float(frequencies[k]),
            period_sessions=1 / float(frequencies[k]),
            power=float(powers[k]),
        )
        for rank, k in enumerate(ranked[: config.max_peaks], 1)
    )
    warnings: list[str] = []
    if degenerate:
        warnings.append("constant_or_trend_only_signal_no_candidate_cycles")
    if config.max_period_sessions is not None and config.max_period_sessions > upper:
        warnings.append("maximum_period_capped_by_required_repetitions")
    return SpectrumResult(
        sample_count=n,
        frequency_resolution=1 / n,
        effective_max_period_sessions=upper,
        cycles=cycles,
        spectrum=tuple(
            SpectrumPoint(
                frequency=float(frequencies[k]),
                period_sessions=1 / float(frequencies[k]),
                power=float(powers[k]),
            )
            for k in indices
        ),
        warnings=tuple(warnings),
    )


def analyze_cycles(
    series: PriceSeries, as_of: date, lookback: int, config: FFTConfig
) -> CycleResult:
    training = series.through(as_of, lookback)
    signal = training.log_prices()
    if config.input == "log_returns":
        signal = np.diff(signal)
    return CycleResult(
        as_of=as_of,
        train_start=training.dates[0],
        forecast_origin=training.dates[-1],
        price_sample_count=len(training.dates),
        config=config,
        analysis=periodogram(signal.tolist(), config),
    )
