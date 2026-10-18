"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError, type SectorResponse, type SymbolsResponse } from "@/lib/api";
import { SectorHistoryChart, SectorRotationChart, sectorColors } from "./charts/SectorCharts";
import { isSessionDate } from "./charts/data";

export function SectorDashboard({ defaultAsOf }: { defaultAsOf?: string }) {
  const [catalog, setCatalog] = useState<SymbolsResponse | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [cutoff, setCutoff] = useState("2025-12-31");
  const [lookback, setLookback] = useState(126);
  const [momentum, setMomentum] = useState(20);
  const [smoothing, setSmoothing] = useState(5);
  const [report, setReport] = useState<SectorResponse | null>(null);
  const [error, setError] = useState<{ message: string; requestId?: string | null } | null>(null);
  const [loading, setLoading] = useState(false);
  const [replaying, setReplaying] = useState(false);
  const [replayed, setReplayed] = useState(false);
  const request = useRef<AbortController | null>(null);
  const version = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    api
      .getSymbols(controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setCatalog(value);
        setError(null);
        setCutoff(
          value.provider === "synthetic-research-v1"
            ? "2022-11-08"
            : value.provider === "synthetic-v1"
              ? "2024-03-28"
              : (defaultAsOf ?? "2025-12-31"),
        );
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(
            cause instanceof ApiError
              ? cause
              : { message: "Cannot load the configured data source." },
          );
      });
    return () => controller.abort();
  }, [attempt, defaultAsOf]);
  useEffect(() => () => request.current?.abort(), []);

  function invalidate() {
    request.current?.abort();
    version.current++;
    setReport(null);
    setError(null);
    setLoading(false);
    setReplaying(false);
    setReplayed(false);
  }
  async function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !isSessionDate(cutoff) ||
      cutoff < "1990-01-01" ||
      cutoff > "2035-12-31" ||
      !Number.isInteger(lookback) ||
      lookback < 32 ||
      lookback > 1260 ||
      !Number.isInteger(momentum) ||
      momentum < 1 ||
      momentum > 126 ||
      !Number.isInteger(smoothing) ||
      smoothing < 1 ||
      smoothing > 30
    ) {
      setError({
        message:
          "Choose a valid cutoff, 32–1,260 reference sessions, 1–126 momentum sessions and 1–30 smoothing sessions.",
      });
      return;
    }
    invalidate();
    const token = version.current;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    try {
      const value = await api.getSectorRotation(
        {
          asOf: cutoff,
          lookbackSessions: lookback,
          momentumSessions: momentum,
          smoothingSessions: smoothing,
        },
        controller.signal,
      );
      if (!controller.signal.aborted && token === version.current) setReport(value);
    } catch (cause) {
      if (!controller.signal.aborted && token === version.current)
        setError(
          cause instanceof ApiError
            ? cause
            : { message: "Sector analysis could not be completed. Please retry." },
        );
    } finally {
      if (token === version.current) setLoading(false);
    }
  }
  async function replay() {
    if (!report) return;
    setReplaying(true);
    setError(null);
    const token = version.current;
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    try {
      await api.replaySector(report.run_id, controller.signal);
      if (token === version.current && !controller.signal.aborted) setReplayed(true);
    } catch (cause) {
      if (token === version.current && !controller.signal.aborted)
        setError(
          cause instanceof ApiError ? cause : { message: "Saved replay could not be verified." },
        );
    } finally {
      if (token === version.current) setReplaying(false);
    }
  }
  const available = catalog?.instruments.some((item) => item.symbol === "XLK");
  const kind = report?.data_kind ?? catalog?.data_kind;
  const result = report?.result;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#sector-workspace">
        Skip to sector workspace
      </a>
      <header className="topbar">
        <Link className="brand" href="/">
          <span className="brand-mark" aria-hidden="true">
            ◉
          </span>
          CycleScope<span className="brand-tag">RESEARCH</span>
        </Link>
        <nav aria-label="Main navigation">
          <Link href="/">Cycle explorer</Link>
          <Link className="nav-active" href="/sectors">
            Sector rotation
          </Link>
          <a href="#sector-method">Methodology</a>
        </nav>
        <div className="top-source">
          <span className={`pill ${kind === "synthetic" ? "pill-amber" : "pill-teal"}`}>
            {kind === "synthetic"
              ? "SYNTHETIC DATA"
              : kind === "real"
                ? "REAL HISTORICAL DATA"
                : "Connecting to data"}
          </span>
        </div>
      </header>
      <main id="sector-workspace">
        <div className="page-heading">
          <div>
            <p className="eyebrow">OBSERVED RELATIVE PERFORMANCE</p>
            <h1>Sector rotation, in context.</h1>
            <p className="lede">
              Compare eight sector ETFs with SPY using matching adjusted observations.
            </p>
          </div>
          <span className="session-tag">Benchmark / SPY · XNYS sessions</span>
        </div>
        <div className="workspace-grid">
          <aside className="controls-panel">
            <div className="controls-title">
              <h2>Comparison setup</h2>
              <span className="muted">SPY</span>
            </div>
            <form onSubmit={run} noValidate>
              <label>
                Sector cutoff
                <input
                  type="date"
                  min="1990-01-01"
                  max="2035-12-31"
                  value={cutoff}
                  onChange={(e) => {
                    invalidate();
                    setCutoff(e.target.value);
                  }}
                />
              </label>
              <label>
                Reference window (trading sessions)
                <input
                  type="number"
                  min={32}
                  max={1260}
                  value={lookback}
                  onChange={(e) => {
                    invalidate();
                    setLookback(Number(e.target.value));
                  }}
                />
              </label>
              <p className="field-help">
                Normalize to 100 at the first session of this window. Changing the reference can
                change quadrant labels.
              </p>
              <label>
                Momentum window (trading sessions)
                <input
                  type="number"
                  min={1}
                  max={126}
                  value={momentum}
                  onChange={(e) => {
                    invalidate();
                    setMomentum(Number(e.target.value));
                  }}
                />
              </label>
              <label>
                Smoothing window (trading sessions)
                <input
                  type="number"
                  min={1}
                  max={30}
                  value={smoothing}
                  onChange={(e) => {
                    invalidate();
                    setSmoothing(Number(e.target.value));
                  }}
                />
              </label>
              <button
                className="button-primary"
                disabled={!available || loading || replaying}
                type="submit"
              >
                Compare sectors<span aria-hidden="true">→</span>
              </button>
            </form>
            <div className="source-note">
              <span className="eyebrow">CONFIGURED SOURCE</span>
              <strong>{catalog?.provider ?? "Awaiting API"}</strong>
              <p>
                SPY plus XLK, XLF, XLE, XLI, XLU, XLV, XLY and XLP. Historical observations only.
              </p>
            </div>
          </aside>
          <div className="results-column">
            {error && (
              <div className="notice notice-error" role="alert">
                <strong>Sector comparison unavailable</strong>
                <p>{error.message}</p>
                {error.requestId && <small>Request {error.requestId}</small>}
                {!catalog && (
                  <button className="button-secondary" onClick={() => setAttempt((x) => x + 1)}>
                    Retry connection
                  </button>
                )}
              </div>
            )}
            {catalog && !available && (
              <div className="notice">
                This dataset does not include sector ETFs. Use the synthetic research dataset or
                load sector observations from the configured market provider.
              </div>
            )}
            {loading && (
              <div className="loading-state" role="status">
                <span className="spinner" aria-hidden="true" />
                Loading matching histories and calculating observed relative strength…
              </div>
            )}
            {!report && !loading && (
              <section className="welcome-panel">
                <p className="eyebrow">EIGHT SECTORS. ONE BENCHMARK.</p>
                <h2>Start with a common reference.</h2>
                <p>
                  Choose a cutoff and windows, then compare sectors. Every ratio uses SPY on the
                  same trading session and adjustment basis.
                </p>
                <div className="welcome-steps">
                  <div>
                    <span>01</span>
                    <strong>Normalize</strong>
                    <p>Sector / SPY, base 100</p>
                  </div>
                  <div>
                    <span>02</span>
                    <strong>Measure</strong>
                    <p>Backward-looking momentum</p>
                  </div>
                  <div>
                    <span>03</span>
                    <strong>Describe</strong>
                    <p>Explicit quadrant rules</p>
                  </div>
                </div>
                <p className="welcome-caveat">
                  These labels describe the chosen history. They do not predict the next leading
                  sector.
                </p>
              </section>
            )}
            {report && result && (
              <div data-testid="sector-results" className="analysis-results">
                <div className="results-context">
                  <div>
                    <p className="eyebrow">COMMON SNAPSHOT</p>
                    <h2>Eight sectors / SPY</h2>
                    <p className="small-note">
                      Observed through {result.observed_through} · reference{" "}
                      {result.normalization_session}
                    </p>
                  </div>
                  <span className="pill">Observed, not forecast</span>
                </div>
                {report.data_kind === "synthetic" && (
                  <div className="notice notice-synthetic">
                    Synthetic sector example. These prices are invented and are not evidence of
                    market rotation or predictive skill.
                  </div>
                )}
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <p className="eyebrow">01 / RELATIVE POSITION</p>
                      <h2>Sector rotation</h2>
                    </div>
                    <span className="pill pill-blue">
                      {result.config.momentum_sessions}-session momentum
                    </span>
                  </div>
                  <p className="small-note">
                    Horizontal: smoothed relative strength index. Vertical: trailing log RS change
                    ×100 (not percentage return).
                  </p>
                  <SectorRotationChart result={result} />
                  <div className="quadrant-key">
                    <span>Leading: above 100, rising</span>
                    <span>Improving: below 100, rising</span>
                    <span>Weakening: above 100, falling</span>
                    <span>Lagging: below 100, falling</span>
                  </div>
                  <p className="small-note">
                    Axes: 100 and 0. Values on either axis (log tolerance 1e−12) are neutral. Labels
                    are descriptive heuristics.
                  </p>
                </section>
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <p className="eyebrow">02 / OBSERVED PATH</p>
                      <h2>Relative strength history</h2>
                    </div>
                    <span className="pill">Reference = 100</span>
                  </div>
                  <SectorHistoryChart result={result} />
                  <p className="small-note">
                    Raw normalized ratios, 100 × (sector / SPY) / reference ratio. Above 100
                    indicates relative appreciation since the reference; it does not require a
                    positive absolute return.
                  </p>
                </section>
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <p className="eyebrow">03 / SNAPSHOT VALUES</p>
                      <h2>Sector observations</h2>
                    </div>
                  </div>
                  <div className="table-wrap">
                    <table
                      className="data-table"
                      aria-label="Sector relative strength observations"
                    >
                      <thead>
                        <tr>
                          <th>Sector</th>
                          <th>Sector / SPY</th>
                          <th>RS index</th>
                          <th>Smoothed index</th>
                          <th>Log change ×100</th>
                          <th>Relative change</th>
                          <th>Quadrant</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.sectors.map((sector, i) => {
                          const point = sector.points.at(-1)!;
                          return (
                            <tr key={sector.ticker}>
                              <td>
                                <span
                                  className="legend-dot"
                                  style={{ background: sectorColors[i] }}
                                />
                                {sector.ticker} <span className="muted">{sector.name}</span>
                              </td>
                              <td>{point.relative_strength.toFixed(5)}</td>
                              <td>{point.normalized_rs.toFixed(3)}</td>
                              <td>{point.smoothed_normalized_rs.toFixed(3)}</td>
                              <td>{(point.momentum_log_rs * 100).toFixed(3)}</td>
                              <td>{point.relative_change_percent.toFixed(3)}%</td>
                              <td className="capitalize">{point.quadrant}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <p className="small-note">
                    Relative change = 100 × (exp(smoothed log momentum) − 1). It measures the
                    price-ratio change over {result.config.momentum_sessions} sessions, not an ETF’s
                    absolute return.
                  </p>
                  <details>
                    <summary>Inspect full observations, configuration and provenance</summary>
                    <pre>{JSON.stringify(report, null, 2)}</pre>
                  </details>
                  <button
                    className="button-secondary replay-button"
                    onClick={replay}
                    disabled={replaying}
                  >
                    Replay sector snapshot
                  </button>
                  {replaying && <p role="status">Replaying retained observations…</p>}
                  {replayed && (
                    <p className="notice" role="status">
                      Exact sector replay verified. No provider request was made.
                    </p>
                  )}
                </section>
              </div>
            )}
            <section className="panel" id="sector-method">
              <div className="panel-heading">
                <h2>Sector methodology</h2>
              </div>
              <div className="method-grid">
                <div>
                  <h3>One feed, matching sessions</h3>
                  <p>
                    RS = sector adjusted close / SPY adjusted close. Missing or mixed-feed histories
                    fail rather than being filled, truncated silently or replaced with another
                    source.
                  </p>
                </div>
                <div>
                  <h3>Trailing log smoothing</h3>
                  <p>
                    The smoothed signal is the trailing mean of log RS. Its index is 100 ×
                    exp(signal − reference signal). Momentum is today’s smoothed log RS minus its
                    value L sessions earlier.
                  </p>
                </div>
                <div>
                  <h3>An explicit reference</h3>
                  <p>
                    The reference is the first session in the displayed window. Additional earlier
                    observations warm up smoothing and momentum. The reference and actual cutoff are
                    retained with each report.
                  </p>
                </div>
                <div>
                  <h3>Descriptive evidence</h3>
                  <p>
                    Labels depend on windows and thresholds. They do not prove persistence, forecast
                    future winners or measure strategy profit. Historical adjustments may include
                    later revisions.
                  </p>
                </div>
              </div>
            </section>
          </div>
        </div>
      </main>
      <footer>
        <span>CycleScope / Observed relative performance</span>
        <span>Recorded adjusted snapshots · No trading predictions</span>
      </footer>
    </div>
  );
}
