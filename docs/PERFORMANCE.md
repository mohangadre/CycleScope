# Measured Week 4 performance

These are observed local request timings, not service-level guarantees or a
production load test. Measurements include serial loopback HTTP, JSON transfer,
database reads, and report persistence for analytical endpoints. There is no
result cache. Processes and PostgreSQL are already running; the first measured
request is **not** a cold-start measurement and OS/database caches may be warm.

The API and PostgreSQL ran in Docker on the same shared x86_64 Linux cloud machine
as the host client. Five logical CPUs were visible in the process affinity mask.
The images use Python 3.12.14, NumPy 2.5.4, SciPy 1.18.1 and PostgreSQL 17.6.
Source/library identity, platform, request settings, timestamps and every measured
latency are recorded in [the raw output](performance/week4.json). Each endpoint
has one first measured call and **20 subsequent serial calls**. Percentiles use
NumPy's default linear interpolation. No concurrent workload or public-network
latency was intentionally generated in the final run.

| Request | First measured | Subsequent p50 | Subsequent p95 |
| --- | ---: | ---: | ---: |
| 720 synthetic SPY price bars, limit 1,000 | 131.5 ms | 36.2 ms | 143.9 ms |
| FFT cycle analysis, 480 observed sessions | 21.0 ms | 21.3 ms | 24.5 ms |
| Eight sectors / SPY, 126/20/5 windows, 150 input sessions each | 192.5 ms | 70.3 ms | 158.4 ms |

The cycle endpoint is below the specification's aspirational two-second small-
window FFT target in this measured run. The price result is below 300 ms at p95,
but this does not establish a cached-read or deployment SLA. Forecast fitting,
bootstrap/backtests, cold process startup, concurrency, larger universes, browser
rendering and naive-DFT/FFT comparisons are outside these measurements. Performance
of those workloads requires separate evidence before making claims.

## Price query correction

The [initial measurement](performance/week4-before-price-projection.json) found
720-bar price reads at p50 861.2 ms and p95 936.0 ms. Inspection showed the ORM join
selected the entire ingestion row, including its retained JSON bar payload, for
each returned daily bar. That multiplied database transfer/JSON decoding without
adding fields to the response.

The query now loads only the needed ingestion metadata (`data_version`,
`fetched_at`, `content_hash`, and ORM primary key), alongside the daily bars.
Price schema, values and provenance are unchanged. The full backend and browser
regression suites passed after the correction. The final recorded price p95 was
143.9 ms. Shared-machine variability and warming prevent attributing the exact
ratio solely to this change; the removed repeated JSON transfer is the concrete
cause addressed. No cache or queue was introduced.

## Reproduce

With the explicit synthetic demo running:

```sh
bash tools/local_demo.sh --no-build
uv run python tools/benchmark_api.py --output .local/performance-week4.json
```

The first command requires previously built images; ordinary first setup uses
`bash tools/local_demo.sh`. In this cloud runner, use `--cloud` and the writable
cache exports in README. The benchmark defaults to cutoff 2022-11-08, start
2020-01-02 and 20 subsequent calls per endpoint. It publishes no market prices
or forecast arrays. It does create ordinary retained analysis/sector reports.
Restore the configured real provider afterward with
`docker compose up -d --wait --no-build api web`.
