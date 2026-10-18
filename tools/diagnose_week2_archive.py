"""Reconstruct archived Week 2 reports; ablations reuse development data.

This forensic tool deliberately imports no current forecasting implementation. It
reconstructs the archived model's documented design matrix from saved parameters.
No model is retrained, and no database or market-data service is accessed.
The real-data report is a private local input, not a checked-in price snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
ROOT = Path(__file__).resolve().parents[1]
ZERO_TOLERANCE = 1e-12


def design(offsets: FloatArray, periods: list[float], scale: int) -> FloatArray:
    """Reconstruct harmonic-ridge-log-price-v1's serialized basis exactly."""
    columns = [np.ones_like(offsets), offsets / scale]
    for period in periods:
        angle = 2 * np.pi * offsets / period
        columns.extend([np.cos(angle), np.sin(angle)])
    return np.column_stack(columns)


def sign(value: float) -> int:
    if abs(value) <= ZERO_TOLERANCE:
        return 0
    return 1 if value > 0 else -1


def metrics(
    actual: FloatArray,
    predicted: FloatArray,
    actual_endpoint_returns: list[float],
    predicted_endpoint_returns: list[float],
) -> dict[str, Any]:
    errors = predicted - actual
    direction_matches = sum(
        sign(realized) == sign(projected)
        for realized, projected in zip(
            actual_endpoint_returns, predicted_endpoint_returns, strict=True
        )
    )
    return {
        "target": "log_adjusted_close",
        "error_unit": "natural_log_price",
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "error_count": len(errors),
        "directional_accuracy": direction_matches / len(actual_endpoint_returns),
        "direction_count": len(actual_endpoint_returns),
        "direction_definition": "horizon_endpoint_return_sign_including_ties",
        "direction_zero_tolerance_log_price": ZERO_TOLERANCE,
    }


def assert_saved_metrics(
    reconstructed: dict[str, Any], archived: dict[str, Any], label: str
) -> None:
    """Fail if a report cannot be reproduced, rather than hiding a mismatch."""
    for key in ("mae", "rmse", "directional_accuracy"):
        if not np.isclose(reconstructed[key], archived[key], rtol=0, atol=1e-12):
            raise ValueError(f"{label}: reconstructed {key} differs from archived metric")
    for key in ("error_count", "direction_count"):
        if reconstructed[key] != archived[key]:
            raise ValueError(f"{label}: reconstructed {key} differs from archived metric")


def diagnose(path: Path, repository: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    document = json.loads(raw)
    envelope = document.get("backtest", document)
    if envelope["schema_version"] != "analysis-v1" or envelope["kind"] != "backtest":
        raise ValueError(f"{path}: expected archived analysis-v1 backtest")
    result = envelope["result"]
    methods = (
        "archived_global_level",
        "posthoc_origin_anchored_harmonic",
        "posthoc_origin_anchored_trend_only",
        "posthoc_origin_anchored_harmonic_without_drift",
        "last_observed_random_walk",
    )
    predictions: dict[str, list[float]] = {method: [] for method in methods}
    endpoint_returns: dict[str, list[float]] = {method: [] for method in methods}
    realized: list[float] = []
    actual_endpoint_returns: list[float] = []
    gaps: list[float] = []
    bootstrap_mean_shifts: list[float] = []
    folds: list[dict[str, Any]] = []
    max_reconstruction_error = 0.0
    excluded_point_count = 0
    for fold in result["folds"]:
        forecast = fold["forecast"]
        fit = forecast["fit"]
        if fit["model_version"] != "harmonic-ridge-log-price-v1":
            raise ValueError(f"{path}: unexpected archived model version")
        count = forecast["training_sample_count"]
        horizon = forecast["horizon_sessions"]
        scale = fit["time_scale_sessions"]
        if scale != count - 1:
            raise ValueError(f"{path}: unexpected archived time scaling")
        coefficients = np.asarray(fit["coefficients"], dtype=np.float64)
        x_train = design(np.arange(count, dtype=np.float64), fit["periods_sessions"], scale)
        x_future = design(
            np.arange(count, count + horizon, dtype=np.float64), fit["periods_sessions"], scale
        )
        origin = float(np.log(forecast["last_observed_price"]))
        fitted_origin = float(x_train[-1] @ coefficients)
        gap = fitted_origin - origin
        gaps.append(gap)
        saved = np.asarray([point["log_value"] for point in forecast["points"]])
        reconstructed = x_future @ coefficients
        reconstruction_error = float(np.max(np.abs(reconstructed - saved)))
        max_reconstruction_error = max(max_reconstruction_error, reconstruction_error)
        if reconstruction_error > 1e-11:
            raise ValueError(f"{path}: saved prediction differs from reconstructed v1 model")
        observed = np.asarray([point["log_value"] for point in fold["realized"]])
        if len(observed) != horizon or len(saved) != horizon:
            raise ValueError(f"{path}: inconsistent fold horizon")
        if abs(fold["baseline_log_price"] - origin) > 1e-12:
            raise ValueError(f"{path}: baseline differs from last observed price")
        trend_change = np.arange(1, horizon + 1) * coefficients[1] / scale
        fold_predictions = {
            "archived_global_level": saved,
            "posthoc_origin_anchored_harmonic": saved - gap,
            "posthoc_origin_anchored_trend_only": origin + trend_change,
            "posthoc_origin_anchored_harmonic_without_drift": saved - gap - trend_change,
            "last_observed_random_walk": np.full(horizon, origin),
        }
        realized.extend(observed.tolist())
        actual_endpoint_returns.append(float(observed[-1] - origin))
        fold_metrics = {}
        for method, projected in fold_predictions.items():
            predictions[method].extend(projected.tolist())
            endpoint_returns[method].append(float(projected[-1] - origin))
            fold_metrics[method] = metrics(
                observed,
                projected,
                [float(observed[-1] - origin)],
                [float(projected[-1] - origin)],
            )
        # Old bootstrap: beta*=A@(X@beta+resampled_centered_residual).
        # Its zero-mean expectation is A@X@beta, not beta under ridge.
        penalty = np.sqrt(fit["ridge_alpha"]) * np.eye(x_train.shape[1])
        penalty[0, 0] = 0
        fit_map = np.linalg.pinv(np.vstack([x_train, penalty]))[:, :count]
        shift = x_future @ (fit_map @ x_train @ coefficients - coefficients)
        bootstrap_mean_shifts.extend(shift.tolist())
        excluded_point_count += sum(
            not point["lower"] <= point["value"] <= point["upper"] for point in forecast["points"]
        )
        folds.append(
            {
                "fold": fold["fold"],
                "train_start": fold["train_start"],
                "train_end": fold["train_end"],
                "test_start": fold["test_start"],
                "test_end": fold["test_end"],
                "training_sample_count": count,
                "training_input_hash": fold["training_input_hash"],
                "saved_periods_sessions": fit["periods_sessions"],
                "observed_origin_log_price": origin,
                "fitted_origin_log_price": fitted_origin,
                "fitted_minus_observed_origin_log_price": gap,
                "first_forecast_return_log_price": float(saved[0] - origin),
                "training_residual_rmse_log_price": fit["training_residual_rmse_log_price"],
                "old_bootstrap_expected_log_shift_min": float(np.min(shift)),
                "old_bootstrap_expected_log_shift_max": float(np.max(shift)),
                "metrics": fold_metrics,
            }
        )
    all_actual = np.asarray(realized, dtype=np.float64)
    pooled = {
        method: metrics(
            all_actual,
            np.asarray(predictions[method], dtype=np.float64),
            actual_endpoint_returns,
            endpoint_returns[method],
        )
        for method in methods
    }
    assert_saved_metrics(
        pooled["archived_global_level"], result["harmonic_metrics"], f"{path}: harmonic"
    )
    assert_saved_metrics(
        pooled["last_observed_random_walk"], result["baseline_metrics"], f"{path}: baseline"
    )
    if len(folds) != result["fold_count"] or len(all_actual) != result["evaluated_forecast_count"]:
        raise ValueError(f"{path}: inconsistent saved evaluation counts")
    return {
        "input_report": (
            str(path.relative_to(repository)) if path.is_relative_to(repository) else path.name
        ),
        "input_report_sha256": hashlib.sha256(raw).hexdigest(),
        "archived_run_id": envelope["run_id"],
        "archived_created_at": envelope["created_at"],
        "archived_source": envelope["source"],
        "archived_software": envelope["software"],
        "archived_config": result["config"],
        "evaluation_status": "reused_development_data",
        "independent_evaluation": False,
        "input_sample_count": result["input_sample_count"],
        "fold_count": len(folds),
        "evaluated_forecast_count": len(all_actual),
        "unscored_sessions_after_initial_training": result[
            "unscored_sessions_after_initial_training"
        ],
        "reconstruction": {
            "saved_predictions_and_original_metrics_verified": True,
            "maximum_saved_prediction_reconstruction_error_log_price": max_reconstruction_error,
        },
        "origin_gap": {
            "definition": "fitted_curve_at_cutoff_minus_last_observed_log_price",
            "minimum": min(gaps),
            "maximum": max(gaps),
            "rmse": float(np.sqrt(np.mean(np.square(gaps)))),
        },
        "old_ridge_bootstrap": {
            "expected_coefficient_formula": "E[beta_star] = A @ X @ beta",
            "centering_defect": "ridge_refit_of_fitted_values_shrinks_coefficients_again",
            "expected_future_log_shift_minimum": min(bootstrap_mean_shifts),
            "expected_future_log_shift_maximum": max(bootstrap_mean_shifts),
            "saved_band_excludes_saved_point_forecast_count": excluded_point_count,
            "bands_are_uncalibrated": True,
        },
        "pooled_metrics": pooled,
        "folds": folds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument(
        "--real-report",
        type=Path,
        help="private archived real report (default: .local/legacy/spy-week2-v1.json)",
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    repository = arguments.repository.resolve()
    output = arguments.output or repository / "docs/experiments/week2-diagnosis.json"
    inputs = [
        repository / "docs/experiments/legacy/synthetic-week2-v1.json",
        (arguments.real_report or repository / ".local/legacy/spy-week2-v1.json").resolve(),
    ]
    if not inputs[0].is_file():
        parser.error(f"Missing checked-in synthetic report: {inputs[0]}")
    if not inputs[1].is_file():
        parser.error(
            "Missing private archived real report. Restore .local/live-week2.json from the "
            "preserved Week 2 checkout.tar.gz to .local/legacy/spy-week2-v1.json, or supply "
            "--real-report PATH to the extracted original. Do not fetch replacement data; "
            "this diagnostic requires the original saved report."
        )
    if output.resolve() in inputs:
        raise ValueError("Diagnostic output must not overwrite an archived input")
    diagnoses = [diagnose(path, repository) for path in inputs]
    artifact = {
        "schema_version": "week2-archive-diagnosis-v1",
        "evaluation_status": "reused_development_data",
        "independent_evaluation": False,
        "tool": {
            "path": "tools/diagnose_week2_archive.py",
            "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "numpy_version": np.__version__,
        },
        "methodology": {
            "original": (
                "saved global harmonic level; reconstructed from saved basis and coefficients"
            ),
            "anchored": "last_log_price + saved_curve(t+h) - saved_curve(t)",
            "trend_only": "last_log_price + saved_trend_coefficient * h / saved_time_scale",
            "without_drift": "anchored harmonic forecast minus saved fitted trend increment",
            "baseline": "last observed log adjusted close at each matching cutoff",
            "aggregation": (
                "pooled errors across every scored offset; direction at horizon endpoint"
            ),
            "retuning": "none; uses archived coefficients, periods, fold boundaries and targets",
        },
        "limitations": [
            "These previously viewed outcomes are development diagnostics, not a fresh holdout.",
            "Anchoring changes the forecast contract from global level to conditional increment.",
            "Trend-only ablation reuses the joint trend; it is not a separately fitted baseline.",
            "Ablations do not measure the new frequency-refinement or bootstrap implementations.",
            "Historical adjusted snapshots have no point-in-time availability guarantee.",
            "No significance, calibrated coverage, profitability or generalization claim is made.",
        ],
        "reports": diagnoses,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False) + "\n")
    for report in diagnoses:
        print(f"{report['input_report']} (reused development data)")
        for method, values in report["pooled_metrics"].items():
            print(f"  {method}: MAE={values['mae']:.9f}, RMSE={values['rmse']:.9f}")
    print(f"Saved deterministic diagnostics to {output}")


if __name__ == "__main__":
    main()
