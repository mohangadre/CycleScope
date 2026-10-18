"use client";

import type { BacktestAnalysis } from "@/lib/api";

interface Props {
  report: BacktestAnalysis;
  onReplay: () => void;
  replaying: boolean;
  replayStatus: string | null;
}

export function BacktestPanel({ report, onReplay, replaying, replayStatus }: Props) {
  const result = report.result;
  const model = result.harmonic_metrics;
  const baseline = result.baseline_metrics;
  const difference = (model.rmse / baseline.rmse - 1) * 100;
  return (
    <section className="panel" data-testid="backtest-results" aria-labelledby="backtest-heading">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">04 / OUT-OF-SAMPLE EVIDENCE</p>
          <h2 id="backtest-heading">Backtest comparison</h2>
        </div>
        <div className="result-badges">
          <span
            className={`pill ${report.source.data_kind === "synthetic" ? "pill-amber" : "pill-teal"}`}
          >
            {report.source.data_kind === "synthetic" ? "Synthetic example" : "Real historical data"}
          </span>
          <span className="pill">{result.fold_count} folds</span>
        </div>
      </div>
      <p className="muted">
        {result.evaluated_forecast_count} scored targets · {result.horizon_sessions}-session horizon
        · {result.config.mode} training · {result.unscored_sessions_after_initial_training} unscored
        sessions
      </p>
      <div className="notice">
        {baseline.rmse === 0
          ? "The random-walk baseline has zero error on this selection."
          : model.rmse === baseline.rmse
            ? "The model and random walk have equal RMSE on this selection."
            : `The harmonic model has ${Math.abs(difference).toFixed(1)}% ${difference > 0 ? "higher" : "lower"} RMSE than random walk on this selection.`}{" "}
        This result does not establish market predictability.
      </div>
      <div className="table-wrap">
        <table className="data-table" aria-label="Backtest metrics">
          <thead>
            <tr>
              <th>Model</th>
              <th>MAE</th>
              <th>RMSE</th>
              <th>Direction accuracy</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <span className="legend-dot blue" />
                Harmonic
              </td>
              <td>{model.mae.toFixed(5)}</td>
              <td>{model.rmse.toFixed(5)}</td>
              <td>
                {(model.directional_accuracy * 100).toFixed(1)}% ({model.direction_count} folds)
              </td>
            </tr>
            <tr>
              <td>
                <span className="legend-dot" />
                Random walk
              </td>
              <td>{baseline.mae.toFixed(5)}</td>
              <td>{baseline.rmse.toFixed(5)}</td>
              <td>
                {(baseline.directional_accuracy * 100).toFixed(1)}% ({baseline.direction_count}{" "}
                folds)
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="small-note">
        MAE/RMSE use natural-log adjusted price, pooled across all scored offsets (
        {model.error_count} matching errors). Direction accuracy scores the horizon-end return sign
        once per fold. Zero returns are a third category; random walk always predicts zero, so its
        score is not a balanced binary-classifier comparison.
      </p>
      <h3>Fold boundaries</h3>
      <div className="table-wrap">
        <table className="data-table" aria-label="Walk-forward folds">
          <thead>
            <tr>
              <th>Fold</th>
              <th>Training interval</th>
              <th>Test interval</th>
              <th>Model RMSE</th>
              <th>Baseline RMSE</th>
            </tr>
          </thead>
          <tbody>
            {result.folds.map((fold) => (
              <tr key={fold.fold}>
                <td>{fold.fold}</td>
                <td>
                  {fold.train_start} → {fold.train_end}
                </td>
                <td>
                  {fold.test_start} → {fold.test_end}
                </td>
                <td>{fold.harmonic_metrics.rmse.toFixed(5)}</td>
                <td>{fold.baseline_metrics.rmse.toFixed(5)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Inspect saved experiment</summary>
        <dl className="provenance-list">
          <dt>Run ID</dt>
          <dd>{report.run_id}</dd>
          <dt>Source</dt>
          <dd>
            {report.source.provider} · {report.source.data_kind}
          </dd>
          <dt>Created (UTC)</dt>
          <dd>{report.created_at}</dd>
          <dt>Input SHA-256</dt>
          <dd>{report.source.input_hash}</dd>
          <dt>Code SHA-256</dt>
          <dd>{report.software.code_sha256}</dd>
        </dl>
        <pre>
          {JSON.stringify(
            {
              schema_version: report.schema_version,
              source: report.source,
              software: report.software,
              config: result.config,
              warnings: result.warnings,
            },
            null,
            2,
          )}
        </pre>
      </details>
      <button className="button-secondary replay-button" disabled={replaying} onClick={onReplay}>
        Replay saved report
      </button>
      <p className="small-note">
        Replay uses the retained snapshot and requires matching code and libraries. It does not
        refresh market prices.
      </p>
      {replayStatus && (
        <p className="notice" role="status">
          {replayStatus}
        </p>
      )}
    </section>
  );
}
