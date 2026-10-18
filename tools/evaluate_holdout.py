"""Freeze, score once, and replay a predeclared retrospective SPY evaluation.

``freeze`` checks existing database coverage and writes the protocol without
contacting Alpaca. ``run`` fetches the fixed interval only after checking the
frozen source/library identity. ``verify`` replays the retained database snapshot
without contacting the provider. Real observations remain in the ignored local
report and PostgreSQL; the published summary contains metrics and provenance.
"""

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from cyclescope.config import Settings
from cyclescope.domain.analysis import BacktestConfig, BacktestResult, HarmonicConfig
from cyclescope.domain.calendar import session_dates
from cyclescope.domain.experiments import AnalysisResponse, BacktestRequest
from cyclescope.domain.models import DateRange
from cyclescope.providers.base import MarketDataProvider
from cyclescope.providers.factory import make_provider
from cyclescope.services.analysis import replay_backtest, run_analysis, software_identity
from cyclescope.services.ingestion import ingest
from cyclescope.storage.database import make_engine
from cyclescope.storage.models import DailyBarRow

PROTOCOL_PATH = Path("docs/experiments/spy-2025-protocol.json")
REPORT_PATH = Path(".local/spy-2025-v2.json")
SUMMARY_PATH = Path("docs/experiments/spy-2025-summary.json")
ATTEMPT_PATH = Path(".local/spy-2025-attempt.json")
TRAIN_START = date(2023, 1, 3)
TRAIN_END = date(2024, 12, 31)
TEST_START = date(2025, 1, 2)
TEST_END = date(2025, 12, 31)
HORIZON = 20

# These are the preserved, unfavorable v1 development results, not a comparison
# on the new evaluation window. They remain evidence of the original failure.
V1_DEVELOPMENT = {
    "label": "previously_viewed_development_diagnostic_not_fresh_holdout",
    "symbol": "SPY",
    "provider": "alpaca-iex",
    "input_start": "2022-01-03",
    "input_end": "2024-12-31",
    "fold_count": 13,
    "evaluated_forecast_count": 260,
    "harmonic_mae_log_price": 0.09448227826322178,
    "harmonic_rmse_log_price": 0.10020777479003992,
    "random_walk_mae_log_price": 0.016978475318262947,
    "random_walk_rmse_log_price": 0.021986290828987908,
}


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def write_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as target:
        target.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def request() -> BacktestRequest:
    train_count = len(session_dates(DateRange(start=TRAIN_START, end=TRAIN_END)))
    return BacktestRequest(
        ticker="SPY",
        start=TRAIN_START,
        end=TEST_END,
        evaluation=BacktestConfig(
            initial_train_sessions=train_count,
            horizon_sessions=HORIZON,
            step_sessions=HORIZON,
            mode="expanding",
            model=HarmonicConfig(seed=17),
        ),
    )


def configured_provider(settings: Settings) -> MarketDataProvider:
    if settings.market_data_provider != "alpaca":
        raise SystemExit("This real-data protocol requires MARKET_DATA_PROVIDER=alpaca")
    return make_provider(settings)


def existing_coverage(engine: Engine, provider: MarketDataProvider) -> dict[str, Any]:
    # Check all symbols for the selected provider, rather than quietly assuming
    # that a previously fetched holdout was never inspected.
    with Session(engine) as session:
        count, latest = session.execute(
            select(func.count(), func.max(DailyBarRow.session_date)).where(
                DailyBarRow.provider == provider.provider_id,
                DailyBarRow.data_kind == "real",
            )
        ).one()
    if latest is not None and latest >= TEST_START:
        raise SystemExit(
            "Provider data from 2025-01-02 onward already exists; this tool cannot "
            "declare an uninspected holdout. Preserve it and choose a new protocol."
        )
    return {
        "provider": provider.provider_id,
        "bar_count": count,
        "latest_session": latest.isoformat() if latest else None,
        "no_stored_provider_observations_on_or_after": TEST_START.isoformat(),
    }


def freeze(engine: Engine, provider: MarketDataProvider) -> None:
    if any(path.exists() for path in (PROTOCOL_PATH, REPORT_PATH, SUMMARY_PATH, ATTEMPT_PATH)):
        raise SystemExit("A protocol or evaluation artifact already exists; refusing overwrite")
    coverage = existing_coverage(engine, provider)
    evaluation = session_dates(DateRange(start=TEST_START, end=TEST_END))
    protocol: dict[str, Any] = {
        "schema_version": "cyclescope-retrospective-holdout-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "request": request().model_dump(mode="json"),
        "software": software_identity().model_dump(mode="json"),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source": {
            "provider": provider.provider_id,
            "data_kind": "real",
            "adjustment_basis": "split_dividend_adjusted",
        },
        "preexisting_database_coverage": coverage,
        "evaluation_design": {
            "training_start": TRAIN_START.isoformat(),
            "initial_training_end": TRAIN_END.isoformat(),
            "first_test_session": evaluation[0].isoformat(),
            "last_available_test_session": evaluation[-1].isoformat(),
            "available_test_sessions": len(evaluation),
            "expected_fold_count": len(evaluation) // HORIZON,
            "expected_evaluated_forecast_count": len(evaluation) // HORIZON * HORIZON,
            "expected_unscored_tail_sessions": len(evaluation) % HORIZON,
            "frequency_selection": "training_only_in_every_fold",
            "configuration_policy": "frozen_before_first_fetch_no_tuning_after_scoring",
            "baseline": "last_observed_log_price_at_each_matching_training_cutoff",
            "error_aggregation": "pooled_log_price_errors_all_20_offsets_per_fold",
            "directional_accuracy": "20_session_endpoint_return_sign_including_zero_ties",
        },
        "original_v1_development_evidence": V1_DEVELOPMENT,
        "limitations": [
            "2022_to_2024_real_data_and_original_synthetic_results_were_development_diagnostics",
            "new_2025_interval_is_retrospective_not_a_live_prospective_trial",
            "adjusted_values_downloaded_now_are_not_point_in_time_available_observations",
            "one_symbol_and_one_year_do_not_establish_predictive_value_or_statistical_significance",
            "report_negative_results_and_do_not_tune_or_select_models_on_this_interval",
            "heuristic_uncertainty_bands_are_not_calibrated_and_coverage_is_not_evaluated",
            "no_trading_profit_or_investment_recommendation_claim",
        ],
    }
    protocol["protocol_sha256"] = canonical_hash(protocol)
    write_new(PROTOCOL_PATH, protocol)
    print(json.dumps({"protocol": str(PROTOCOL_PATH), **protocol["evaluation_design"]}, indent=2))


def read_protocol() -> dict[str, Any]:
    protocol: dict[str, Any] = json.loads(PROTOCOL_PATH.read_text())
    saved_hash = protocol.get("protocol_sha256")
    contents = {key: value for key, value in protocol.items() if key != "protocol_sha256"}
    if canonical_hash(contents) != saved_hash:
        raise SystemExit("Protocol integrity check failed")
    if protocol.get("schema_version") != "cyclescope-retrospective-holdout-v1":
        raise SystemExit("Unsupported protocol version")
    current = software_identity().model_dump(mode="json")
    saved = protocol["software"]
    if current["code_sha256"] != saved["code_sha256"] or current["libraries"] != saved["libraries"]:
        raise SystemExit("Source or library identity differs from the frozen protocol")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != protocol["runner_sha256"]:
        raise SystemExit("Evaluation runner differs from the frozen protocol")
    if request().model_dump(mode="json") != protocol["request"]:
        raise SystemExit("Fixed request or defaults differ from the frozen protocol")
    return protocol


def check_result(response: AnalysisResponse, protocol: dict[str, Any]) -> BacktestResult:
    if not isinstance(response.result, BacktestResult):
        raise SystemExit("Saved result is not a backtest")
    result = response.result
    design = protocol["evaluation_design"]
    actual = (
        result.fold_count,
        result.evaluated_forecast_count,
        result.unscored_sessions_after_initial_training,
    )
    expected = (
        design["expected_fold_count"],
        design["expected_evaluated_forecast_count"],
        design["expected_unscored_tail_sessions"],
    )
    if actual != expected or result.folds[0].test_start != TEST_START:
        raise SystemExit("Fold boundaries or score counts differ from the frozen design")
    if any(fold.test_start < TEST_START for fold in result.folds):
        raise SystemExit("Evaluation includes a target from the development interval")
    if response.source.provider != protocol["source"]["provider"]:
        raise SystemExit("Saved provider differs from the frozen protocol")
    return result


def run(engine: Engine, provider: MarketDataProvider) -> None:
    protocol = read_protocol()
    if provider.provider_id != protocol["source"]["provider"]:
        raise SystemExit("Configured feed differs from the frozen protocol")
    if any(path.exists() for path in (REPORT_PATH, SUMMARY_PATH, ATTEMPT_PATH)):
        raise SystemExit("Evaluation was already attempted; use verify, never overwrite its result")
    existing_coverage(engine, provider)
    # This exclusive marker precedes the first HTTP request. Failed or interrupted
    # attempts remain visible for manual review rather than silently rescoring.
    write_new(
        ATTEMPT_PATH,
        {
            "started_at": datetime.now(UTC).isoformat(),
            "protocol_sha256": protocol["protocol_sha256"],
            "request": protocol["request"],
        },
    )
    ingestion_id = ingest(engine, provider, "SPY", DateRange(start=TRAIN_START, end=TEST_END))
    response = run_analysis(
        engine, provider, "SPY", BacktestRequest.model_validate(protocol["request"])
    )
    result = check_result(response, protocol)
    if replay_backtest(engine, response.run_id) != response:
        raise SystemExit("Persisted-snapshot replay differed from the scored response")
    write_new(REPORT_PATH, response.model_dump(mode="json"))
    summary = {
        "schema_version": "cyclescope-retrospective-holdout-summary-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "protocol_sha256": protocol["protocol_sha256"],
        "run_id": str(response.run_id),
        "ingestion_run_id": str(ingestion_id),
        "source": response.source.model_dump(mode="json"),
        "software": response.software.model_dump(mode="json"),
        "request": protocol["request"],
        "local_report": str(REPORT_PATH),
        "local_report_sha256": hashlib.sha256(REPORT_PATH.read_bytes()).hexdigest(),
        "snapshot_replay": "exact_match_without_provider_request",
        "fold_count": result.fold_count,
        "evaluated_forecast_count": result.evaluated_forecast_count,
        "unscored_tail_sessions": result.unscored_sessions_after_initial_training,
        "harmonic_metrics": result.harmonic_metrics.model_dump(mode="json"),
        "baseline_metrics": result.baseline_metrics.model_dump(mode="json"),
        "folds": [
            {
                "fold": fold.fold,
                "train_start": fold.train_start.isoformat(),
                "train_end": fold.train_end.isoformat(),
                "test_start": fold.test_start.isoformat(),
                "test_end": fold.test_end.isoformat(),
                "training_input_hash": fold.training_input_hash,
                "harmonic_metrics": fold.harmonic_metrics.model_dump(mode="json"),
                "baseline_metrics": fold.baseline_metrics.model_dump(mode="json"),
            }
            for fold in result.folds
        ],
        "original_v1_development_evidence": protocol["original_v1_development_evidence"],
        "limitations": protocol["limitations"],
    }
    write_new(SUMMARY_PATH, summary)
    print(
        json.dumps(
            {
                "summary": str(SUMMARY_PATH),
                "local_report": str(REPORT_PATH),
                "run_id": str(response.run_id),
                "fold_count": result.fold_count,
                "evaluated_forecast_count": result.evaluated_forecast_count,
                "harmonic_metrics": summary["harmonic_metrics"],
                "baseline_metrics": summary["baseline_metrics"],
            },
            indent=2,
        )
    )


def verify(engine: Engine) -> None:
    protocol = read_protocol()
    summary = json.loads(SUMMARY_PATH.read_text())
    if summary["protocol_sha256"] != protocol["protocol_sha256"]:
        raise SystemExit("Summary does not refer to the frozen protocol")
    if hashlib.sha256(REPORT_PATH.read_bytes()).hexdigest() != summary["local_report_sha256"]:
        raise SystemExit("Local report integrity check failed")
    response = AnalysisResponse.model_validate_json(REPORT_PATH.read_text())
    if str(response.run_id) != summary["run_id"]:
        raise SystemExit("Summary and local report identify different saved runs")
    check_result(response, protocol)
    if replay_backtest(engine, response.run_id) != response:
        raise SystemExit("Persisted-snapshot replay differed from the saved local report")
    print("Frozen protocol, local report hash, and saved-snapshot replay verified; no provider I/O")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "verify"))
    args = parser.parse_args()
    settings = Settings()
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        if args.command == "freeze":
            freeze(engine, configured_provider(settings))
        elif args.command == "run":
            run(engine, configured_provider(settings))
        else:
            verify(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
