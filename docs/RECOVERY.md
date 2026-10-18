# Historical experiment recovery

Before Week 4, the working Week 3 checkout and PostgreSQL database were preserved
outside the repository at `/workspace/.cyclescope-recovery/week3-before-week4/`:

- `checkout.tar.gz`: source, fixtures, lock files, docs and private local reports;
  excludes Git metadata, environments, node modules, build outputs and credentials.
- `database.dump`: PostgreSQL custom-format recovery copy, not a migration script.
- `SHA256SUMS`: archive/dump integrity hashes.
- `extracted/`: separately extracted Week 3 source with its own locked runtime.

The original Week 2 rollback archive remains untouched at
`/workspace/.cyclescope-recovery/week2-rollback-6144a953f450`.
These recovery files contain private historical market observations. They are
outside the checkout and must not be published as public fixture artifacts.

The prepared machine's historical verification was run from `extracted/`:

```sh
UV_CACHE_DIR=/workspace/.cache/uv uv sync --frozen
MARKET_DATA_PROVIDER=alpaca ALPACA_FEED=iex UV_CACHE_DIR=/workspace/.cache/uv uv run python tools/evaluate_holdout.py verify
```

This installs the archived package version 0.2.1 in its own `.venv`, verifies the
frozen 2025 protocol and local report hash, and exactly replays the retained
database snapshot without contacting Alpaca. It passed after the new Week 4 data
ingestion. The original report therefore survives changes to latest stored bars.

The active package is 0.4.0. Its package-wide source/library identity differs, so
strict replay of that older run returns 409; GET still returns original JSON.
Do not change a saved protocol's hash, overwrite a result, or declare previously
viewed historical data an untouched holdout. Current Week 4 reports have their own
software identity and replay normally.

Recovery archives are local preservation, not a replacement for repository commits,
remote backups, or a verified new-task environment snapshot. No destructive database
restore was needed or performed. A database restore should first target a separate
database and be checked before any replacement of active storage.
