# Actual browser screenshots

These PNGs were copied unchanged from the successful Chromium fixture tests using
the real PostgreSQL-backed API and production Next.js build. All prices and
financial results in these screenshots are explicitly **synthetic** demonstrations.
They are not mockups or real market observations.

- `week4-sectors-desktop.png`: 1280-pixel desktop sector dashboard, two charts,
  eight-sector observation table and successful saved replay.
- `week4-sectors-mobile.png`: 390-pixel mobile layout with a horizontally scrollable
  table and no page overflow.
- `week4-cycles.png`: desktop price/cycle/forecast/backtest workflow with actual
  returned fixture metrics, source labeling and replay.

Regenerate with a normal frontend production build and:

```sh
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium uv run python tools/run_frontend_e2e.py
```

Success screenshots are generated under ignored `frontend/test-results/` and may
contain changing run IDs/timestamps. The source labels, returned values and chart
content are checked by the browser tests. Real-data browser evidence stays private
under `.local/` and is not copied here.
