"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import {
  api,
  ApiError,
  type BacktestAnalysis,
  type CycleAnalysis,
  type FFTConfig,
  type ForecastAnalysis,
  type PriceHistory,
  type SymbolsResponse,
} from "@/lib/api";
import { ForecastChart, HistoricalPriceChart, SpectrumChart } from "./charts";
import { isSessionDate } from "./charts/data";
import { BacktestPanel } from "./BacktestPanel";

interface Selection {
  ticker: string;
  start: string;
  end: string;
  lookback: number;
  horizon: number;
  initial: number;
  input: FFTConfig["input"];
  detrend: FFTConfig["detrend"];
  window: FFTConfig["window"];
  mode: "expanding" | "rolling";
}

const initialSelection: Selection = {
  ticker: "SPY",
  start: "2023-01-03",
  end: "2025-12-31",
  lookback: 480,
  horizon: 20,
  initial: 480,
  input: "detrended_log_adjusted_close",
  detrend: "linear",
  window: "hann",
  mode: "expanding",
};

function defaults(provider: string, defaultAsOf?: string, defaultStart?: string): Selection {
  if (provider === "synthetic-research-v1")
    return { ...initialSelection, start: "2020-01-02", end: "2022-11-08" };
  if (provider === "synthetic-v1")
    return {
      ...initialSelection,
      start: "2024-01-02",
      end: "2024-03-28",
      lookback: 40,
      initial: 40,
      horizon: 10,
    };
  return {
    ...initialSelection,
    start: defaultStart ?? initialSelection.start,
    end: defaultAsOf ?? initialSelection.end,
  };
}

const dollars = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});
function errorDetails(error: unknown): { message: string; id?: string | null } {
  if (error instanceof ApiError) return { message: error.message, id: error.requestId };
  return { message: "The request could not be completed. Please retry." };
}

function validate(selection: Selection): string | null {
  if (
    !isSessionDate(selection.start) ||
    !isSessionDate(selection.end) ||
    selection.start > selection.end
  )
    return "Choose a valid date range: start must be on or before end.";
  if (selection.start < "1990-01-01" || selection.end > "2035-12-31")
    return "Choose dates within 1990–2035.";
  if ((Date.parse(selection.end) - Date.parse(selection.start)) / 86_400_000 > 3660)
    return "The date range cannot exceed 3,660 calendar days.";
  if (
    !Number.isInteger(selection.lookback) ||
    selection.lookback < (selection.input === "log_returns" ? 33 : 32) ||
    selection.lookback > 2520
  )
    return "Lookback must contain 32–2,520 trading sessions (at least 33 for log returns).";
  if (!Number.isInteger(selection.horizon) || selection.horizon < 1 || selection.horizon > 63)
    return "Choose a forecast horizon from 1–63 trading sessions.";
  if (!Number.isInteger(selection.initial) || selection.initial < 32 || selection.initial > 1260)
    return "Initial training must contain 32–1,260 trading sessions.";
  return null;
}

function SourceBadge({ kind }: { kind: "real" | "synthetic" }) {
  return (
    <span className={`pill ${kind === "synthetic" ? "pill-amber" : "pill-teal"}`}>
      <span className="status-dot" />
      {kind === "synthetic" ? "SYNTHETIC DATA" : "REAL HISTORICAL DATA"}
    </span>
  );
}

export function Dashboard({
  defaultAsOf,
  defaultStart,
}: {
  defaultAsOf?: string;
  defaultStart?: string;
}) {
  const [catalog, setCatalog] = useState<SymbolsResponse | null>(null);
  const [catalogError, setCatalogError] = useState<ReturnType<typeof errorDetails> | null>(null);
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [selection, setSelection] = useState(initialSelection);
  const [prices, setPrices] = useState<PriceHistory | null>(null);
  const [analysis, setAnalysis] = useState<{
    cycles: CycleAnalysis;
    forecast: ForecastAnalysis;
  } | null>(null);
  const [backtest, setBacktest] = useState<BacktestAnalysis | null>(null);
  const [error, setError] = useState<ReturnType<typeof errorDetails> | null>(null);
  const [busy, setBusy] = useState<"analysis" | "backtest" | "replay" | null>(null);
  const [replayStatus, setReplayStatus] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null);
  const epoch = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    api
      .getSymbols(controller.signal)
      .then((symbols) => {
        if (controller.signal.aborted) return;
        setCatalog(symbols);
        setCatalogError(null);
        setSelection(defaults(symbols.provider, defaultAsOf, defaultStart));
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setCatalogError(errorDetails(cause));
      });
    return () => controller.abort();
  }, [catalogAttempt, defaultAsOf, defaultStart]);

  useEffect(() => () => active.current?.abort(), []);

  function change<Key extends keyof Selection>(key: Key, value: Selection[Key]) {
    active.current?.abort();
    epoch.current += 1;
    setSelection((previous) => ({ ...previous, [key]: value }));
    if (key !== "initial" && key !== "mode") {
      setPrices(null);
      setAnalysis(null);
    }
    setBacktest(null);
    setError(null);
    setBusy(null);
    setReplayStatus(null);
  }

  function begin(stage: "analysis" | "backtest" | "replay") {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    const version = ++epoch.current;
    setBusy(stage);
    setError(null);
    return { controller, current: () => version === epoch.current && !controller.signal.aborted };
  }

  async function runAnalysis(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const invalid = validate(selection);
    if (invalid) {
      setError({ message: invalid });
      return;
    }
    const request = begin("analysis");
    setPrices(null);
    setAnalysis(null);
    setBacktest(null);
    setReplayStatus(null);
    try {
      const history = await api.getPrices(
        { ticker: selection.ticker, start: selection.start, end: selection.end },
        request.controller.signal,
      );
      if (!request.current()) return;
      if (!history.bars.length) {
        setError({
          message:
            "No stored price history for this selection. Choose a covered date range or ingest data for the configured provider.",
        });
        return;
      }
      setPrices(history);
      if (history.bars.length < selection.lookback)
        throw new ApiError(
          `This range has ${history.bars.length} observations. Reduce the lookback or select more history; ${selection.lookback} sessions are required.`,
          "insufficient_data",
          422,
        );
      const query = {
        ticker: selection.ticker,
        asOf: selection.end,
        lookback: selection.lookback,
        input: selection.input,
        detrend: selection.detrend,
        window: selection.window,
      };
      const [cycles, forecast] = await Promise.all([
        api.getCycles(query, request.controller.signal),
        api.getForecast(
          { ...query, horizonSessions: selection.horizon },
          request.controller.signal,
        ),
      ]);
      if (!request.current()) return;
      if (
        cycles.source.input_hash !== forecast.source.input_hash ||
        forecast.source.provider !== history.provider ||
        forecast.source.data_kind !== history.data_kind ||
        forecast.source.ticker !== history.ticker ||
        forecast.result.last_observed_price !== Number(history.bars.at(-1)?.close)
      )
        throw new ApiError(
          "The data changed while the analysis was running. Run the analysis again to use a consistent snapshot.",
          "snapshot_changed",
          409,
        );
      setAnalysis({ cycles, forecast });
    } catch (cause) {
      if (request.current()) {
        setError(errorDetails(cause));
        request.controller.abort();
      }
    } finally {
      if (active.current === request.controller) setBusy(null);
    }
  }

  async function runBacktest() {
    const invalid = validate(selection);
    if (invalid) {
      setError({ message: invalid });
      return;
    }
    if (!prices || prices.bars.length < selection.initial + selection.horizon) {
      setError({
        message:
          "Select enough stored history for initial training followed by a complete forecast horizon.",
      });
      return;
    }
    if (Math.floor((prices.bars.length - selection.initial) / selection.horizon) > 20) {
      setError({
        message:
          "This selection would exceed 20 folds. Increase initial training or the horizon, or shorten the date range.",
      });
      return;
    }
    const request = begin("backtest");
    setBacktest(null);
    setReplayStatus(null);
    try {
      const report = await api.runBacktest(
        {
          ticker: selection.ticker,
          start: selection.start,
          end: selection.end,
          initialTrainSessions: selection.initial,
          horizonSessions: selection.horizon,
          mode: selection.mode,
          input: selection.input,
          detrend: selection.detrend,
          window: selection.window,
        },
        request.controller.signal,
      );
      if (request.current()) setBacktest(report);
    } catch (cause) {
      if (request.current()) setError(errorDetails(cause));
    } finally {
      if (active.current === request.controller) setBusy(null);
    }
  }

  async function replay() {
    if (!backtest) return;
    const request = begin("replay");
    setReplayStatus(null);
    try {
      const report = await api.replayBacktest(backtest.run_id, request.controller.signal);
      if (request.current()) {
        setBacktest(report);
        setReplayStatus(
          "Exact replay verified from the saved snapshot. No market-data request was made.",
        );
      }
    } catch (cause) {
      if (request.current()) setError(errorDetails(cause));
    } finally {
      if (active.current === request.controller) setBusy(null);
    }
  }

  const rows =
    prices?.bars.map((bar) => ({ session_date: bar.session_date, close: Number(bar.close) })) ?? [];
  const firstPrice = rows[0]?.close;
  const lastPrice = rows.at(-1)?.close;
  const changePercent = firstPrice && lastPrice ? (lastPrice / firstPrice - 1) * 100 : null;
  const forecast = analysis?.forecast.result;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace">
        Skip to research workspace
      </a>
      <header className="topbar">
        <Link className="brand" href="/" aria-label="CycleScope home">
          <span className="brand-mark" aria-hidden="true">
            ◉
          </span>
          CycleScope<span className="brand-tag">RESEARCH</span>
        </Link>
        <nav aria-label="Main navigation">
          <a className="nav-active" href="#workspace">
            Cycle explorer
          </a>
          <Link href="/sectors">Sector rotation</Link>
          <a href="#methodology">
            Methodology <span aria-hidden="true">↗</span>
          </a>
        </nav>
        <div className="top-source">
          {catalog ? (
            <SourceBadge kind={catalog.data_kind} />
          ) : (
            <span className="pill">Connecting to data</span>
          )}
        </div>
      </header>
      <main id="workspace">
        <div className="page-heading">
          <div>
            <p className="eyebrow">THE CYCLE EXPLORER</p>
            <h1>Patterns need evidence.</h1>
            <p className="lede">
              Explore historical cycles. Inspect projections. Test them against a baseline.
            </p>
          </div>
          <span className="session-tag">
            <span className="status-dot" />
            Daily observations · XNYS
          </span>
        </div>
        <div className="workspace-grid">
          <aside className="controls-panel">
            <div className="controls-title">
              <h2>Research setup</h2>
              <span className="muted">01</span>
            </div>
            <form onSubmit={runAnalysis} noValidate>
              <label>
                Ticker
                <select
                  aria-label="Ticker"
                  value={selection.ticker}
                  disabled={!catalog}
                  onChange={(e) => change("ticker", e.target.value)}
                >
                  {catalog?.instruments.map((instrument) => (
                    <option key={instrument.symbol} value={instrument.symbol}>
                      {instrument.symbol} · {instrument.display_name}
                    </option>
                  )) ?? <option value="SPY">Loading symbols…</option>}
                </select>
              </label>
              <div className="field-row">
                <label>
                  Start date
                  <input
                    type="date"
                    min="1990-01-01"
                    max="2035-12-31"
                    value={selection.start}
                    onChange={(e) => change("start", e.target.value)}
                  />
                </label>
                <label>
                  End date
                  <input
                    type="date"
                    min="1990-01-01"
                    max="2035-12-31"
                    value={selection.end}
                    onChange={(e) => change("end", e.target.value)}
                  />
                </label>
              </div>
              <p className="field-help">
                Dates select stored observations. The end date sets the requested forecast cutoff.
              </p>
              <label>
                Lookback (trading sessions)
                <input
                  type="number"
                  min={32}
                  max={2520}
                  value={selection.lookback}
                  onChange={(e) => change("lookback", Number(e.target.value))}
                />
              </label>
              <label>
                Forecast horizon (trading sessions)
                <input
                  type="number"
                  min={1}
                  max={63}
                  value={selection.horizon}
                  onChange={(e) => change("horizon", Number(e.target.value))}
                />
              </label>
              <label>
                Spectrum input
                <select
                  value={selection.input}
                  onChange={(e) => change("input", e.target.value as Selection["input"])}
                >
                  <option value="detrended_log_adjusted_close">Detrended log price</option>
                  <option value="log_returns">Log returns</option>
                </select>
              </label>
              <div className="field-row">
                <label>
                  Detrending
                  <select
                    value={selection.detrend}
                    onChange={(e) => change("detrend", e.target.value as Selection["detrend"])}
                  >
                    <option value="linear">Linear</option>
                    <option value="constant">Mean</option>
                  </select>
                </label>
                <label>
                  Window
                  <select
                    value={selection.window}
                    onChange={(e) => change("window", e.target.value as Selection["window"])}
                  >
                    <option value="hann">Hann</option>
                    <option value="boxcar">Boxcar</option>
                  </select>
                </label>
              </div>
              <button className="button-primary" disabled={!catalog || busy !== null} type="submit">
                Run analysis<span aria-hidden="true">↗</span>
              </button>
              <div className="control-divider" />
              <p className="eyebrow">WALK-FORWARD EVALUATION</p>
              <label>
                Initial training (trading sessions)
                <input
                  type="number"
                  min={32}
                  max={1260}
                  value={selection.initial}
                  onChange={(e) => change("initial", Number(e.target.value))}
                />
              </label>
              <label>
                Training window
                <select
                  value={selection.mode}
                  onChange={(e) => change("mode", e.target.value as Selection["mode"])}
                >
                  <option value="expanding">Expanding</option>
                  <option value="rolling">Rolling</option>
                </select>
              </label>
              <p className="field-help">
                Nonoverlapping tests use the same horizon. Each fold selects and fits its own model.
              </p>
              <button
                className="button-secondary"
                type="button"
                disabled={!prices || busy !== null}
                onClick={runBacktest}
              >
                Run backtest<span aria-hidden="true">→</span>
              </button>
            </form>
            <div className="source-note">
              <span className="eyebrow">CONFIGURED SOURCE</span>
              <strong>{catalog?.provider ?? "Awaiting API"}</strong>
              <p>Stored adjusted prices. No live quotes or automatic data downloads.</p>
            </div>
          </aside>
          <div className="results-column">
            {catalogError && (
              <div role="alert" className="notice notice-error">
                <strong>Data connection unavailable</strong>
                <p>{catalogError.message}</p>
                {catalogError.id && <small>Request {catalogError.id}</small>}
                <button
                  className="button-secondary"
                  onClick={() => setCatalogAttempt((attempt) => attempt + 1)}
                >
                  Retry connection
                </button>
              </div>
            )}
            {error && (
              <div role="alert" className="notice notice-error">
                <strong>Unable to complete this request</strong>
                <p>{error.message}</p>
                {error.id && <small>Request {error.id}</small>}
              </div>
            )}
            {busy && (
              <div className="loading-state" role="status" aria-live="polite">
                <span className="spinner" aria-hidden="true" />
                {busy === "analysis"
                  ? "Running analysis: loading observations and fitting training-only models…"
                  : busy === "backtest"
                    ? "Running walk-forward backtest…"
                    : "Replaying the saved snapshot…"}
              </div>
            )}
            {!prices && !busy && (
              <section className="welcome-panel">
                <div className="orbit-art" aria-hidden="true">
                  <div />
                  <div />
                  <div />
                  <span>ƒ</span>
                </div>
                <p className="eyebrow">FROM PATTERN TO TESTABLE HYPOTHESIS</p>
                <h2>Start with the observations.</h2>
                <p>
                  Choose a ticker and date range, then run an analysis to see what the historical
                  signal contains.
                </p>
                <div className="welcome-steps">
                  <div>
                    <span>01</span>
                    <strong>Observe</strong>
                    <p>Adjusted price history</p>
                  </div>
                  <div>
                    <span>02</span>
                    <strong>Investigate</strong>
                    <p>Cycles and future projections</p>
                  </div>
                  <div>
                    <span>03</span>
                    <strong>Evaluate</strong>
                    <p>Model versus random walk</p>
                  </div>
                </div>
                <p className="welcome-caveat">
                  A spectral peak is a candidate, not proof of a future cycle.
                </p>
              </section>
            )}
            {prices && (
              <div data-testid="analysis-results" className="analysis-results">
                <div className="results-context">
                  <div>
                    <span className="eyebrow">RESEARCH SNAPSHOT</span>
                    <h2>
                      {prices.ticker}
                      <span className="muted"> / {prices.provider}</span>
                    </h2>
                  </div>
                  <SourceBadge kind={prices.data_kind} />
                </div>
                {prices.data_kind === "synthetic" && (
                  <div className="notice notice-synthetic">
                    Synthetic example: these are invented prices for software testing, not observed
                    market performance.
                  </div>
                )}
                <div className="summary-grid">
                  <div>
                    <span>Last observed close</span>
                    <strong>{lastPrice ? dollars.format(lastPrice) : "—"}</strong>
                    <small>USD per share · {rows.at(-1)?.session_date}</small>
                  </div>
                  <div>
                    <span>Observed range change</span>
                    <strong>
                      {changePercent === null
                        ? "—"
                        : `${changePercent >= 0 ? "+" : ""}${changePercent.toFixed(2)}%`}
                    </strong>
                    <small>Historical change, not forecast return</small>
                  </div>
                  <div>
                    <span>Stored observations</span>
                    <strong>{prices.total.toLocaleString("en-US")}</strong>
                    <small>
                      {rows[0]?.session_date} → {rows.at(-1)?.session_date}
                    </small>
                  </div>
                </div>
                {prices.warnings.length > 0 && (
                  <div className="notice">
                    <strong>Data notes</strong>
                    <ul>
                      {prices.warnings.map((warning) => (
                        <li key={warning}>{warning.replaceAll("_", " ")}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <section className="panel" aria-labelledby="history-heading">
                  <div className="panel-heading">
                    <div>
                      <p className="eyebrow">01 / OBSERVATIONS</p>
                      <h2 id="history-heading">Price history</h2>
                    </div>
                    <span className="pill">Adjusted close · USD</span>
                  </div>
                  <HistoricalPriceChart points={rows} ticker={prices.ticker} />
                  <details>
                    <summary>Inspect observed values</summary>
                    <div className="table-wrap">
                      <table className="data-table" aria-label="Observed price values">
                        <thead>
                          <tr>
                            <th>Trading session</th>
                            <th>Adjusted close (USD)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {prices.bars.map((bar) => (
                            <tr key={bar.session_date}>
                              <td>{bar.session_date}</td>
                              <td>{bar.close}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                </section>
                {analysis && forecast && (
                  <>
                    <section className="panel" aria-labelledby="cycles-heading">
                      <div className="panel-heading">
                        <div>
                          <p className="eyebrow">02 / HISTORICAL SIGNAL</p>
                          <h2 id="cycles-heading">Candidate cycles</h2>
                        </div>
                        <span className="pill pill-amber">Significance not tested</span>
                      </div>
                      <p className="muted">
                        {analysis.cycles.result.price_sample_count} prices through{" "}
                        {analysis.cycles.result.forecast_origin} · {selection.detrend} detrending ·{" "}
                        {selection.window} window
                      </p>
                      <SpectrumChart
                        points={analysis.cycles.result.analysis.spectrum}
                        candidatePeriods={analysis.cycles.result.analysis.cycles.map(
                          (cycle) => cycle.period_sessions,
                        )}
                      />
                      <div className="table-wrap">
                        <table className="data-table" aria-label="Candidate cycle periods">
                          <thead>
                            <tr>
                              <th>Period (trading sessions)</th>
                              <th>Power density</th>
                              <th>Evidence</th>
                            </tr>
                          </thead>
                          <tbody>
                            {analysis.cycles.result.analysis.cycles.map((cycle) => (
                              <tr key={cycle.rank}>
                                <td>{cycle.period_sessions.toFixed(2)}</td>
                                <td>{cycle.power.toPrecision(5)}</td>
                                <td>Not tested</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      {analysis.cycles.result.analysis.cycles.length === 0 && (
                        <p className="notice">
                          No candidate cycles found with these settings. A trend-only forecast may
                          still be returned.
                        </p>
                      )}
                      <p className="small-note">
                        FFT resolution:{" "}
                        {analysis.cycles.result.analysis.frequency_resolution.toPrecision(4)}{" "}
                        cycles/session. Periods are trading sessions. Peak prominence does not
                        establish significance.
                      </p>
                    </section>
                    <section className="panel" aria-labelledby="forecast-heading">
                      <div className="panel-heading">
                        <div>
                          <p className="eyebrow">03 / EXPLORATORY PROJECTION</p>
                          <h2 id="forecast-heading">Forecast</h2>
                        </div>
                        <span className="pill pill-blue">
                          {forecast.horizon_sessions} future sessions
                        </span>
                      </div>
                      <p className="muted">
                        Observed through the cutoff <strong>{forecast.forecast_origin}</strong>.
                        Projected values begin {forecast.points[0]?.session_date}.
                      </p>
                      <ForecastChart
                        history={rows}
                        points={forecast.points}
                        asOf={forecast.forecast_origin}
                        ticker={prices.ticker}
                        turningWindows={forecast.turning_points}
                      />
                      <div className="notice">
                        Uncalibrated uncertainty band. Training residuals are resampled in circular
                        blocks; empirical coverage has not been evaluated. This is not a calibrated
                        confidence interval.
                      </div>
                      <h3>Candidate turning windows</h3>
                      <p className="small-note">
                        Local extrema of the future projection only. Windows use a heuristic ±
                        {forecast.config.turn_window_tolerance_sessions} trading-session tolerance.
                      </p>
                      {forecast.turning_points.length > 0 ? (
                        <div className="table-wrap">
                          <table className="data-table" aria-label="Forecast turning windows">
                            <thead>
                              <tr>
                                <th>Candidate</th>
                                <th>Projected session</th>
                                <th>Heuristic window</th>
                              </tr>
                            </thead>
                            <tbody>
                              {forecast.turning_points.map((turn) => (
                                <tr key={`${turn.kind}-${turn.session_offset}`}>
                                  <td className="capitalize">{turn.kind}</td>
                                  <td>
                                    {turn.session_date} (+{turn.session_offset})
                                  </td>
                                  <td>
                                    {turn.window_start} → {turn.window_end}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="muted">
                          No interior turning points detected within this horizon.
                        </p>
                      )}
                      <details>
                        <summary>Inspect projected values and model</summary>
                        <div className="table-wrap">
                          <table className="data-table" aria-label="Projected price values">
                            <thead>
                              <tr>
                                <th>Future session</th>
                                <th>Projection (USD)</th>
                                <th>Uncalibrated lower</th>
                                <th>Uncalibrated upper</th>
                              </tr>
                            </thead>
                            <tbody>
                              {forecast.points.map((point) => (
                                <tr key={point.session_date}>
                                  <td>{point.session_date}</td>
                                  <td>{point.value.toFixed(4)}</td>
                                  <td>{point.lower.toFixed(4)}</td>
                                  <td>{point.upper.toFixed(4)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <pre>
                          {JSON.stringify(
                            {
                              run_id: analysis.forecast.run_id,
                              source: analysis.forecast.source,
                              software: analysis.forecast.software,
                              train_start: forecast.train_start,
                              train_end: forecast.train_end,
                              model: forecast.fit,
                              config: forecast.config,
                              uncertainty: forecast.uncertainty,
                              warnings: forecast.warnings,
                            },
                            null,
                            2,
                          )}
                        </pre>
                      </details>
                    </section>
                  </>
                )}
              </div>
            )}
            {backtest && (
              <BacktestPanel
                report={backtest}
                onReplay={replay}
                replaying={busy === "replay"}
                replayStatus={replayStatus}
              />
            )}
            {prices && !backtest && (
              <section className="panel evaluation-placeholder">
                <p className="eyebrow">04 / EVIDENCE</p>
                <h2>Test the projection.</h2>
                <p>
                  Run a walk-forward backtest to compare matching out-of-sample errors with the
                  last-observed-price baseline. Each fold fits using its training observations only.
                </p>
              </section>
            )}
            <section className="panel methodology" id="methodology">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">READ THE ASSUMPTIONS</p>
                  <h2>Method and provenance</h2>
                </div>
              </div>
              <div className="method-grid">
                <div>
                  <h3>Training-only analysis</h3>
                  <p>
                    Log-price or log-return FFT candidates are selected at the cutoff. Up to three
                    frequencies are refined within half-bin bounds. Harmonic ridge regression always
                    models log adjusted close.
                  </p>
                </div>
                <div>
                  <h3>A conditional projection</h3>
                  <p>
                    The model adds fitted future changes to the last observed log price. This
                    carries the terminal residual forward; it is a modeling assumption, not evidence
                    that cycles predict markets.
                  </p>
                </div>
                <div>
                  <h3>Evidence before interpretation</h3>
                  <p>
                    Spectral significance is not tested. Bands and turning windows are uncalibrated.
                    Adjusted historical snapshots may contain later revisions and do not guarantee
                    point-in-time availability.
                  </p>
                </div>
                <div>
                  <h3>Matching baselines</h3>
                  <p>
                    Walk-forward errors are compared with random walk at matching cutoffs and
                    targets. Negative results are valid. No profitability or investment
                    recommendation is implied.
                  </p>
                </div>
              </div>
            </section>
          </div>
        </div>
      </main>
      <footer>
        <span>
          CycleScope <span className="muted">/ Research with a record.</span>
        </span>
        <span>Historical data · Exploratory models · Reproducible evidence</span>
      </footer>
    </div>
  );
}
