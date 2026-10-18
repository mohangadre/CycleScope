from datetime import date

import numpy as np
import pytest
from scipy.signal import periodogram as scipy_periodogram

from cyclescope.analytics.fourier import analyze_cycles, periodogram
from cyclescope.analytics.series import PriceSeries
from cyclescope.domain.analysis import FFTConfig
from cyclescope.domain.calendar import session_dates
from cyclescope.domain.errors import InsufficientData
from cyclescope.domain.models import DateRange


def signal_series(n: int = 720) -> PriceSeries:
    dates = session_dates(DateRange(start=date(2020, 1, 2), end=date(2024, 12, 31)))[:n]
    t = np.arange(n)
    prices = np.exp(4 + 0.0002 * t + 0.04 * np.sin(2 * np.pi * t / 40))
    return PriceSeries(dates, tuple(prices.tolist()))


@pytest.mark.parametrize("period", [40, 120])
@pytest.mark.parametrize("window", ["boxcar", "hann"])
def test_known_frequencies(period: int, window: str) -> None:
    n = 960
    values = np.sin(2 * np.pi * np.arange(n) / period)
    result = periodogram(values.tolist(), FFTConfig(window=window, detrend="constant"))
    strongest = result.cycles[0]
    assert strongest.period_sessions == pytest.approx(period)
    assert strongest.frequency == pytest.approx(1 / period)
    assert result.frequency_resolution == 1 / n
    assert strongest.significance_status == "not_tested"


def test_two_harmonics_and_seeded_noise() -> None:
    rng = np.random.default_rng(42)
    t = np.arange(960)
    values = (
        np.sin(2 * np.pi * t / 40) + 0.7 * np.sin(2 * np.pi * t / 120) + rng.normal(0, 0.2, len(t))
    )
    result = periodogram(values.tolist(), FFTConfig(max_peaks=2))
    assert {cycle.period_sessions for cycle in result.cycles} == {40, 120}


def test_periodogram_normalization_matches_scipy_and_parseval() -> None:
    values = np.random.default_rng(4).normal(size=512)
    config = FFTConfig(window="boxcar", detrend="constant", min_period_sessions=2)
    result = periodogram(values.tolist(), config)
    frequencies, powers = scipy_periodogram(
        values, fs=1, window="boxcar", detrend="constant", scaling="density"
    )
    for point in result.spectrum:
        k = round(point.frequency * len(values))
        assert point.frequency == frequencies[k]
        assert point.power == pytest.approx(powers[k], rel=1e-12, abs=1e-12)
    # k=1 is excluded because it cannot show two observed repetitions.
    assert (sum(point.power for point in result.spectrum) + powers[1]) / len(
        values
    ) == pytest.approx(np.var(values))


@pytest.mark.parametrize("values", [np.ones(256), np.zeros(256), 3 + 0.2 * np.arange(256)])
def test_degenerate_signals_have_no_candidates(values: np.ndarray) -> None:
    result = periodogram(values.tolist(), FFTConfig())
    assert result.cycles == ()
    assert all(point.power == 0 for point in result.spectrum)
    assert "constant_or_trend_only_signal_no_candidate_cycles" in result.warnings


def test_nyquist_is_supported_and_dc_excluded() -> None:
    values = (-1.0) ** np.arange(128)
    result = periodogram(
        values.tolist(), FFTConfig(min_period_sessions=2, detrend="constant", window="boxcar")
    )
    assert result.cycles[0].period_sessions == 2
    assert all(point.frequency > 0 for point in result.spectrum)


@pytest.mark.parametrize("values", [[], [1] * 31, [1] * 2521, [1] * 40 + [np.nan], [np.inf] * 40])
def test_invalid_signals(values: list[float]) -> None:
    with pytest.raises(InsufficientData):
        periodogram(values, FFTConfig())


def test_period_bounds_require_multiple_repetitions() -> None:
    values = np.sin(np.arange(64)).tolist()
    result = periodogram(values, FFTConfig(max_period_sessions=120, min_repetitions=3))
    assert result.effective_max_period_sessions == 64 / 3
    assert all(point.period_sessions <= 64 / 3 for point in result.spectrum)
    assert "maximum_period_capped_by_required_repetitions" in result.warnings
    with pytest.raises(InsufficientData, match="too short"):
        periodogram(values, FFTConfig(min_period_sessions=40))


def test_random_walk_peaks_make_no_significance_claim() -> None:
    values = np.random.default_rng(8).normal(size=720).cumsum()
    result = periodogram(values.tolist(), FFTConfig())
    assert len(result.cycles) <= 3
    assert all(cycle.significance_status == "not_tested" for cycle in result.cycles)
    assert result.model_dump_json() == periodogram(values.tolist(), FFTConfig()).model_dump_json()


def test_cutoff_ignores_appended_and_corrupt_future_before_preprocessing() -> None:
    full = signal_series()
    cutoff = full.dates[479]
    prefix = PriceSeries(full.dates[:480], full.closes[:480])
    changed = PriceSeries(full.dates, full.closes[:480] + (float("nan"),) * 240)
    for input_type in ("detrended_log_adjusted_close", "log_returns"):
        config = FFTConfig(input=input_type)
        result = analyze_cycles(prefix, cutoff, 480, config)
        assert result == analyze_cycles(full, cutoff, 480, config)
        assert result == analyze_cycles(changed, cutoff, 480, config)
        assert result.analysis.sample_count == (479 if input_type == "log_returns" else 480)


@pytest.mark.parametrize(
    "problem", ["duplicate", "gap", "weekend", "negative", "zero", "nan", "empty"]
)
def test_session_and_price_validation(problem: str) -> None:
    original = signal_series(100)
    dates, prices = list(original.dates), list(original.closes)
    if problem == "duplicate":
        dates[10] = dates[9]
    elif problem == "gap":
        del dates[10]
        del prices[10]
    elif problem == "weekend":
        dates[1] = date(2020, 1, 4)
    elif problem == "empty":
        dates, prices = [], []
    else:
        prices[10] = {"negative": -1, "zero": 0, "nan": float("nan")}[problem]
    with pytest.raises(InsufficientData):
        analyze_cycles(
            PriceSeries(tuple(dates), tuple(prices)), original.dates[-1], len(dates), FFTConfig()
        )


def test_stale_origin_and_insufficient_lookback() -> None:
    series = signal_series(100)
    with pytest.raises(InsufficientData, match="cutoff"):
        analyze_cycles(series, date(2024, 12, 31), 100, FFTConfig())
    with pytest.raises(InsufficientData, match="Need 101"):
        analyze_cycles(series, series.dates[-1], 101, FFTConfig())
