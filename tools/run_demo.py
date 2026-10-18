"""Run and optionally verify the offline Week 2 experiment against PostgreSQL.

No market credentials or provider HTTP requests are used. Output is SYNTHETIC.
"""

import argparse
import json
from datetime import date
from pathlib import Path

from cyclescope.config import Settings
from cyclescope.domain.analysis import BacktestConfig, HarmonicConfig
from cyclescope.domain.experiments import BacktestRequest, CycleRequest, ForecastRequest
from cyclescope.domain.models import DateRange
from cyclescope.providers.synthetic import SyntheticProvider
from cyclescope.services.analysis import replay_backtest, run_analysis
from cyclescope.services.ingestion import ingest
from cyclescope.storage.database import make_engine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".local/synthetic-week2.json"))
    parser.add_argument(
        "--verify", type=Path, help="Compare inputs and numerical result to a recorded report"
    )
    args = parser.parse_args()
    engine = make_engine(Settings().database_url.get_secret_value())
    provider = SyntheticProvider(research=True)
    try:
        batch = provider.get_daily_bars("SPY", date(2020, 1, 2), date(2024, 12, 31))
        start, end = batch.bars[0].session_date, batch.bars[-1].session_date
        ingest(engine, provider, "SPY", DateRange(start=start, end=end))
        cycles = run_analysis(engine, provider, "SPY", CycleRequest(as_of=end, lookback=480))
        prediction = run_analysis(
            engine, provider, "SPY", ForecastRequest(as_of=end, lookback=480, horizon_sessions=40)
        )
        result = run_analysis(
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
        assert replay_backtest(engine, result.run_id) == result
        body = result.model_dump(mode="json")
        if args.verify:
            reference = json.loads(args.verify.read_text())
            if (
                reference["source"]["input_hash"] != body["source"]["input_hash"]
                or reference["result"] != body["result"]
            ):
                raise SystemExit(
                    "Reference mismatch: inputs or numerical results differ; "
                    "inspect recorded software/runtime"
                )
            print("Reference input and numerical result reproduced exactly")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(body, indent=2, allow_nan=False) + "\n")
        print(
            json.dumps(
                {
                    "data_kind": "synthetic",
                    "output": str(args.output),
                    "run_id": str(result.run_id),
                    "input_hash": result.source.input_hash,
                    "cycles": cycles.result.model_dump(mode="json")
                    .get("analysis", {})
                    .get("cycles"),
                    "forecast_points": len(
                        prediction.result.model_dump(mode="json").get("points", [])
                    ),
                    "backtest": {
                        key: body["result"][key]
                        for key in (
                            "fold_count",
                            "evaluated_forecast_count",
                            "harmonic_metrics",
                            "baseline_metrics",
                        )
                    },
                },
                indent=2,
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
