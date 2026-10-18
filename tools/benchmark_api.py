"""Record serial local HTTP latency; no result cache, prices or forecasts are published."""

import argparse
import json
import os
import platform
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import numpy as np

from cyclescope.services.analysis import software_identity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--as-of", default="2022-11-08")
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path(".local/performance-week4.json"))
    args = parser.parse_args()
    if not 5 <= args.repeats <= 100:
        parser.error("repeats must be between 5 and 100")
    paths = {
        "prices": "/api/v1/prices/SPY?"
        + urlencode({"start": args.start, "end": args.as_of, "limit": 1000}),
        "cycles": "/api/v1/cycles/SPY?" + urlencode({"as_of": args.as_of, "lookback": 480}),
        "sectors": "/api/v1/sectors/rotation?"
        + urlencode(
            {
                "as_of": args.as_of,
                "lookback_sessions": 126,
                "momentum_sessions": 20,
                "smoothing_sessions": 5,
            }
        ),
    }
    measurements = {}
    for name, path in paths.items():
        latencies = []
        for _ in range(args.repeats + 1):
            started = time.perf_counter()
            with urllib.request.urlopen(args.base_url.rstrip("/") + path, timeout=30) as response:
                payload = json.load(response)
                if response.status != 200:
                    raise RuntimeError("Benchmark request failed")
            latencies.append(1000 * (time.perf_counter() - started))
        source = payload.get("source", payload)
        measurements[name] = {
            "request_path": path,
            "provider": source["provider"],
            "data_kind": source["data_kind"],
            "first_measured_ms": latencies[0],
            "warm_request_count": args.repeats,
            "warm_ms": latencies[1:],
            "warm_p50_ms": float(np.percentile(latencies[1:], 50)),
            "warm_p95_ms": float(np.percentile(latencies[1:], 95)),
            "warm_max_ms": max(latencies[1:]),
        }
    report = {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "scope": (
            "Serial loopback HTTP including JSON transfer, database reads, and report persistence; "
            "no result cache. Not a cold-start or concurrency benchmark."
        ),
        "cache_note": (
            "Processes and database already running; OS/database caches may already be warm, "
            "including the first measured request."
        ),
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "process_cpu_affinity_count": len(os.sched_getaffinity(0))
            if hasattr(os, "sched_getaffinity")
            else None,
        },
        "software": software_identity().model_dump(mode="json"),
        "measurements": measurements,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                name: {
                    key: value
                    for key, value in stats.items()
                    if key in ("first_measured_ms", "warm_p50_ms", "warm_p95_ms", "data_kind")
                }
                for name, stats in measurements.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
