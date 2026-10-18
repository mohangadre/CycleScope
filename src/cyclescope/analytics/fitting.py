"""Bounded training-only variable projection and fixed-design ridge algebra."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares

from cyclescope.domain.analysis import FrequencyRefinement, HarmonicConfig
from cyclescope.domain.errors import InsufficientData


def design_matrix(
    t: NDArray[np.float64], periods: tuple[float, ...], scale: int
) -> NDArray[np.float64]:
    columns = [np.ones_like(t), t / scale]
    for period in periods:
        columns.extend([np.cos(2 * np.pi * t / period), np.sin(2 * np.pi * t / period)])
    return np.column_stack(columns)


def bootstrap_coefficients(
    coefficients: NDArray[np.float64],
    fit_map: NDArray[np.float64],
    sampled_training_residuals: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Return (coefficient, draw) perturbations without applying ridge shrinkage twice.

    Residual draws have shape (draw, training observation). With zero-mean draws,
    the conditional expectation is exactly the original coefficient vector.
    """
    return coefficients[:, None] + fit_map @ sampled_training_residuals.T


def _ridge_system(
    y: NDArray[np.float64], periods: tuple[float, ...], alpha: float
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    x = design_matrix(np.arange(len(y), dtype=np.float64), periods, len(y) - 1)
    penalty = np.sqrt(alpha) * np.eye(x.shape[1])
    penalty[0, 0] = 0  # The intercept is never penalized.
    return x, np.vstack([x, penalty]), np.r_[y, np.zeros(x.shape[1])]


def _objective(
    y: NDArray[np.float64], x: NDArray[np.float64], beta: NDArray[np.float64], alpha: float
) -> float:
    residuals = y - x @ beta
    return float(residuals @ residuals + alpha * (beta[1:] @ beta[1:]))


@dataclass(frozen=True)
class HarmonicSolution:
    design: NDArray[np.float64]
    coefficients: NDArray[np.float64]
    fit_map: NDArray[np.float64]
    refinement: FrequencyRefinement


def fit_harmonics(
    y: NDArray[np.float64],
    initial_periods: tuple[float, ...],
    fft_sample_count: int,
    config: HarmonicConfig,
) -> HarmonicSolution:
    """Refine only within each candidate's half-bin, using the training ridge objective.

    Optimization variables are frequencies measured in FFT bins for well-scaled
    numerical derivatives. Each residual evaluation eliminates the linear ridge
    coefficients by least squares. The bounded solver's max_nfev excludes its
    finite-difference Jacobian calls (at most three extra calls per evaluation).
    Failed/non-improving solves retain the original FFT frequencies.
    """
    x, augmented, target = _ridge_system(y, initial_periods, config.ridge_alpha)
    try:
        fit_map = np.linalg.pinv(augmented)[:, : len(y)]
    except np.linalg.LinAlgError as exc:
        raise InsufficientData("Harmonic fit failed to converge") from exc
    beta = fit_map @ y
    initial_objective = _objective(y, x, beta, config.ridge_alpha)
    upper_period = min(
        config.fft.max_period_sessions or float(fft_sample_count),
        fft_sample_count / config.fft.min_repetitions,
    )
    minimum_frequency = 1 / upper_period
    maximum_frequency = min(0.5, 1 / config.fft.min_period_sessions)
    bins = np.array([fft_sample_count / period for period in initial_periods])
    lower = np.maximum(bins - 0.5, minimum_frequency * fft_sample_count)
    upper = np.minimum(bins + 0.5, maximum_frequency * fft_sample_count)
    bounds = tuple(
        (float(lo / fft_sample_count), float(hi / fft_sample_count))
        for lo, hi in zip(lower, upper, strict=True)
    )
    metadata = FrequencyRefinement(
        status="no_cycles" if not initial_periods else "disabled",
        initial_periods_sessions=initial_periods,
        fitted_periods_sessions=initial_periods,
        frequency_bounds=bounds,
        initial_objective=initial_objective,
        final_objective=initial_objective,
        nfev=0,
        converged=None,
    )
    free = np.flatnonzero(upper - lower > 64 * np.finfo(float).eps)
    if not initial_periods or not config.refine_frequencies:
        return HarmonicSolution(x, beta, fit_map, metadata)
    if not len(free):
        return HarmonicSolution(
            x, beta, fit_map, metadata.model_copy(update={"status": "unchanged"})
        )

    def residuals(candidate: NDArray[np.float64]) -> NDArray[np.float64]:
        frequencies = bins.copy()
        frequencies[free] = candidate
        periods = tuple((fft_sample_count / frequencies).tolist())
        _, matrix, observations = _ridge_system(y, periods, config.ridge_alpha)
        coefficients = np.linalg.lstsq(matrix, observations, rcond=None)[0]
        return matrix @ coefficients - observations

    try:
        result = least_squares(
            residuals,
            np.clip(bins[free], lower[free], upper[free]),
            bounds=(lower[free], upper[free]),
            max_nfev=config.frequency_refinement_max_nfev,
            ftol=1e-11,
            xtol=1e-11,
            gtol=1e-11,
        )
        metadata = metadata.model_copy(
            update={"nfev": int(result.nfev), "converged": bool(result.success)}
        )
        if not result.success:
            return HarmonicSolution(
                x, beta, fit_map, metadata.model_copy(update={"status": "fallback_not_converged"})
            )
        final_bins = bins.copy()
        final_bins[free] = result.x
        periods = tuple((fft_sample_count / final_bins).tolist())
        refined_x, matrix, _ = _ridge_system(y, periods, config.ridge_alpha)
        refined_map = np.linalg.pinv(matrix)[:, : len(y)]
        refined_beta = refined_map @ y
        final_objective = _objective(y, refined_x, refined_beta, config.ridge_alpha)
    except (np.linalg.LinAlgError, ValueError, FloatingPointError):
        return HarmonicSolution(
            x, beta, fit_map, metadata.model_copy(update={"status": "fallback_numerical_failure"})
        )
    if not np.isfinite(final_objective) or final_objective > initial_objective:
        return HarmonicSolution(
            x, beta, fit_map, metadata.model_copy(update={"status": "fallback_no_improvement"})
        )
    # Leave exact-grid solutions unchanged rather than perturbing a numerical zero.
    floor = 64 * np.finfo(float).eps * max(1.0, initial_objective)
    if initial_objective - final_objective <= floor:
        return HarmonicSolution(
            x, beta, fit_map, metadata.model_copy(update={"status": "unchanged"})
        )
    return HarmonicSolution(
        refined_x,
        refined_beta,
        refined_map,
        metadata.model_copy(
            update={
                "status": "refined",
                "fitted_periods_sessions": periods,
                "final_objective": final_objective,
            }
        ),
    )
