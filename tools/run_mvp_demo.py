"""Persist and reproduce the complete Week 4 SYNTHETIC experiment, without credentials."""

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from cyclescope.config import Settings
from cyclescope.domain.analysis import BacktestConfig, HarmonicConfig
from cyclescope.domain.experiments import BacktestRequest, CycleRequest, ForecastRequest
from cyclescope.domain.models import CATALOG, DateRange
from cyclescope.domain.sectors import SectorRequest
from cyclescope.providers.synthetic import SyntheticProvider
from cyclescope.services.analysis import replay_backtest, run_analysis
from cyclescope.services.ingestion import ingest
from cyclescope.services.sectors import replay_sector, run_sector
from cyclescope.storage.database import make_engine


def comparable(report: dict[str, Any]) -> dict[str, Any]:
    """Compare source content and numerical outputs; audit IDs/times may change."""
    return {
        name: {
            "input_hash": report[name].get(
                "input_hash", report[name].get("source", {}).get("input_hash")
            ),
            "result": report[name]["result"],
        }
        for name in ("cycles", "forecast", "backtest", "sectors")
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".local/synthetic-mvp-week4.json"))
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    start, end = date(2020, 1, 2), date(2022, 11, 8)
    provider = SyntheticProvider(research=True)
    engine = make_engine(Settings().database_url.get_secret_value())
    try:
        for instrument in CATALOG:
            ingest(engine, provider, instrument.symbol, DateRange(start=start, end=end))
        cycles = run_analysis(engine, provider, "SPY", CycleRequest(as_of=end, lookback=480))
        prediction = run_analysis(
            engine, provider, "SPY", ForecastRequest(as_of=end, lookback=480, horizon_sessions=40)
        )
        evaluation = run_analysis(
            engine,
            provider,
            "SPY",
            BacktestRequest(
                ticker="SPY",
                start=start,
                end=end,
                evaluation=BacktestConfig(
                    initial_train_sessions=480, horizon_sessions=20, model=HarmonicConfig(seed=17)
                ),
            ),
        )
        sectors = run_sector(engine, provider, SectorRequest(as_of=end))
        if replay_backtest(engine, evaluation.run_id) != evaluation:
            raise RuntimeError("Backtest snapshot replay differed")
        if replay_sector(engine, sectors.run_id) != sectors:
            raise RuntimeError("Sector snapshot replay differed")
        report = {
            "demo_version": "synthetic-mvp-week4-v1",
            "data_kind": "synthetic",
            "notice": "Invented fixtures demonstrate software behavior, not market predictability.",
            "cycles": cycles.model_dump(mode="json"),
            "forecast": prediction.model_dump(mode="json"),
            "backtest": evaluation.model_dump(mode="json"),
            "sectors": sectors.model_dump(mode="json"),
        }
        if args.verify:
            reference = json.loads(args.verify.read_text())
            if reference.get("demo_version") != report["demo_version"] or comparable(
                reference
            ) != comparable(report):
                raise SystemExit(
                    "Reference mismatch: inspect source inputs and numerical/runtime differences"
                )
            print("All four input hashes and numerical results reproduced exactly")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(
            json.dumps(
                {
                    "data_kind": "synthetic",
                    "output": str(args.output),
                    "instruments": len(CATALOG),
                    "research_bars": 720 * len(CATALOG),
                    "forecast_points": len(prediction.result.points),
                    "backtest_folds": evaluation.result.fold_count,
                    "sectors": len(sectors.result.sectors),
                    "sector_observations_each": sectors.result.config.lookback_sessions,
                    "saved_snapshot_replays": "exact: backtest and sectors",
                },
                indent=2,
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
