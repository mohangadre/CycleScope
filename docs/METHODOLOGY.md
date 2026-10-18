# Data and numerical methodology

CycleScope tests candidate financial cycles with retained data, explicit numerical
contracts and matching baselines. Software correctness does not establish that
cycles persist or forecasts have trading value. Original unfavorable Week 2 results
remain visible; the corrected model also lost on a separately frozen real interval.

## Data, calendar and provenance

OHLC is split/dividend-adjusted USD per share; volume is shares. Stored prices use
`NUMERIC(22,8)` and serialize as decimal strings. Daily dates are exchange-session
labels; fetch/ingestion timestamps are UTC instants. Validate positive finite prices,
OHLC ordering, integer nonnegative volume, ordered unique dates, and complete expected
session coverage. Reject gaps/non-session bars rather than interpolating. Ingestion
is transactional per symbol. Never mix providers, feeds or adjustment bases.

The fixed 1990–2035 XNYS calendar includes US equity holidays and extraordinary
closures. This is the documented session mapping for the supported US equity/ETF
universe, not every exchange. Sampling uses trading sessions, not weekends or
252/365-day arithmetic. Future dates follow the last training session. A weekend/
holiday `as_of` selects the prior session; missing cutoff data fails.

Alpaca requests `adjustment=all`, explicit IEX/SIP feed, ascending daily bars and
inclusive New York date boundaries. End is the requested day's final microsecond
(`23:59:59.999999`); next midnight can include an unwanted daily bar. This correction
remains a Week 1 fix. IDs `alpaca-iex`/`alpaca-sip` separate feeds. IEX is not
consolidated market volume. Provider licensing, entitlements and revisions apply.

Each ingestion retains normalized payload, source/feed version, interval,
timestamps and SHA-256. Latest bars reference their last ingestion run; revised
data leaves earlier snapshots intact. Application snapshots are append-only by
convention; administrators can modify them. Analysis retains selected dates/closes,
hash, source/ingestion references, configuration, package source hash, Git revision
where available, library versions and outputs. Analysis never refreshes implicitly.
Readiness checks the database/schema, not feed freshness or keys.

**Point-in-time limitation:** adjusted snapshots were retrieved after historical
cutoffs. Providers can revise corporate-action adjustments. Algorithmic cutoff
isolation does not prove historical data availability. These are retrospective
evaluations on recorded adjusted snapshots, not executable trading simulations.

## Synthetic fixtures

Unchanged `synthetic_v1.json` contains 61 sessions per symbol, 2024-01-02 through
2024-03-28 (244 bars). Its deterministic generator uses symbol index `i` and session
index `t`: `close = round(100 + 25*i + 0.1*t + 4*sin(2*pi*t/40), 4)`, with consistent
invented OHLC and volume.

`synthetic_research_v1.csv` contains 720 sessions per symbol, 2020-01-02 through
2022-11-08 (2,880 bars). NumPy PCG64 uses seed `1729+i`:

```
log close[t] = log(100+25*i) + 0.0002*t
               + 0.04*sin(2*pi*t/40) + 0.025*cos(2*pi*t/120)
               + Normal(0, 0.003)
```

The generator rounds to eight decimals and constructs consistent invented OHLC/
volume. Both profiles say `data_kind: synthetic`. Regeneration is checked with the
locked runtime. Separate analytic signals, including nonaligned sample lengths and
off-grid periods, test numerical recovery without claiming market predictability.

## FFT candidate cycles

1. Select exactly `lookback` consecutive observations at/before `as_of`, then
   validate and transform. Log returns produce `lookback-1` signal samples. Require
   32–2,520 finite signal samples.
2. Remove a linear least-squares trend (default) or mean (`constant`). Residuals
   below 64 machine epsilons times raw signal scale are treated as numerical zero.
3. Apply periodic Hann (default) or boxcar. Compute `rfft` without zero padding:
   `f[k]=k/N` cycles/session and `T[k]=1/f[k]` sessions. Frequency resolution is `1/N`.
4. Normalize `P[k]=|FFT(window*x)[k]|²/sum(window²)`, doubling positive interior bins
   but not Nyquist. Sampling frequency is one session⁻¹. The one-sided PSD unit is
   input units squared per cycles/session. Its integrated full spectrum equals the
   window-weighted mean-square residual; tests compare against SciPy.
5. Exclude DC. Minimum period defaults to four sessions (minimum allowed two);
   maximum defaults to `N/min_repetitions` (two observed cycles). Respect explicit
   maximum/repetition settings and report history caps. Fail if no bins qualify.
6. Find local maxima with prominence (default 5% of largest eligible power) and
   bin spacing. Rank by power with deterministic ties, allowing a genuine Nyquist
   peak; return up to five candidates (default three).

`selected_cycles` retain these coarse bin periods/powers. Every candidate says
`significance_status: not_tested`. Prominence/rank is not statistical significance,
persistence, a p-value or evidence of forecast accuracy.

## Harmonic fit and conditional projection — v2

The model targets log adjusted close, even when log returns select candidate
periods. With at most three harmonics:

```
m(t) = beta0 + beta1*t/(N-1)
       + sum(a_k*cos(2*pi*t/T_k) + b_k*sin(2*pi*t/T_k))
```

Ridge defaults to 0.01 on every coefficient except intercept. An augmented-system
SVD pseudoinverse supports zero penalty and rank deficiency. Coefficients retain
the displayed column order; `time_scale_sessions=N-1` defines the trend unit. No
peaks yields an explicitly flagged trend-only fit.

By default, bounded variable projection refines frequencies using training data
only. Start at selected FFT bins; search within ±half a frequency bin, clipped by
period/repetition limits and adjacent candidate neighborhoods. For each trial,
solve ridge coefficients and minimize training squared log residuals plus ridge
penalty. The bounded solver has a recorded evaluation budget; failure or
nonconvergence falls back to original frequencies with an explicit status. This
parametric refinement does not change the periodogram's `1/N` resolution or create
statistical significance. Configurations can disable refinement.

`fit.frequency_refinement` records initial/fitted periods, frequency bounds,
initial/final objectives, status, convergence and evaluations. `fit.periods_sessions`
are the fitted periods, distinct from coarse `selected_cycles`.

Let the last training observation be `y(T)` with `T=N-1`. The v2 forecast is:

```
predicted_log(T+h) = y(T) + m(T+h) - m(T),  h=1,...,H
```

This conditional fitted-change contract anchors horizon zero to the observed price.
The archived v1 model extrapolated the global level `m(T+h)`, allowing a large gap
from the latest observation. Unconditional regression is mathematically legitimate;
anchoring changes the model assumption by carrying the observed terminal residual
forward. It does not prove that the learned changes predict returns. Persist
`observed_origin_log_price`, `fitted_origin_log_price`, their difference
`origin_adjustment_log_price`, and `projection_method: conditional_fitted_change`.
The model identifier is `harmonic-increment-log-price-v2`.

Project onto future exchange sessions, exponentiate to USD/share, and reject
invalid/overflowing values. Offset one is the first future session. Detect extrema
only from the forecast log curve, with default prominence 0.001 log-price units and
three-session minimum separation. Endpoints cannot confirm a local extremum. Default
±2-session windows are clipped to the horizon and labeled
`heuristic_session_tolerance`; they are not timing probabilities.

## Uncalibrated residual-change bootstrap

Center training residuals; use local PCG64 seed (default zero), circular blocks of
five sessions, and 100 draws (bounded 50–500). Let `A` be the fixed-frequency ridge
fit map, `beta` the original fit, and `e*` a sampled residual path. Use
`beta* = beta + A @ e*_train`. This centers coefficient draws on the fitted estimate.
The old `A @ (X @ beta + e*_train)` applies ridge shrinkage twice because generally
`A @ X @ beta != beta`.

Anchor every draw using the fitted-change contract:

```
y*(T+h) = y(T) + (X[T+h]-X[T]) @ beta* + e*(T+h)-e*(T)
```

Exponentiate predictive log quantiles. Default central residual quantile mass is
0.9; it is not a calibrated 90% market prediction/confidence level. The method
`training_residual_change_block_bootstrap` assumes stationary additive regression
residuals and fixes selected/refined frequencies. Frequency-selection/refinement
uncertainty is omitted (`frequency_selection_uncertainty_included: false`). Outputs
say `exploratory_uncalibrated_band`, `calibrated: false`, and
`uncertainty_coverage_not_evaluated`. All residuals come from training data.

## Walk-forward folds and metrics

Initial training defaults to 360 sessions, rolling or expanding. Each fold trains
through its cutoff and evaluates a complete future horizon (default 20). Step
defaults to horizon; overlapping steps are rejected. Larger steps can leave gaps.
Omit incomplete terminal horizons, report unscored sessions, and cap at 20 folds.
Every fold redoes preprocessing, selection/refinement, fitting and bootstrap using
only its training slice. Save boundaries, input hashes, coefficients, periods,
projections and actual targets. Tests modify post-cutoff data and assert unchanged
earlier forecasts. Realized turning-point labels never enter model inputs;
turning-point accuracy and band coverage evaluation remain unimplemented.

Random walk carries forward the last observed log adjusted close at identical
cutoffs, dates and targets. For `e=predicted_log-actual_log`, MAE is
`sum(abs(e))/error_count`; RMSE is `sqrt(sum(e²)/error_count)`. Pool errors across all
scored offsets/folds. Units are natural-log price, not dollars or percentages.

Directional accuracy scores horizon-end return signs relative to the origin once
per fold (`direction_count`). Ties are a third category; absolute log changes up to
1e-12 count as zero. Random walk predicts zero, so it is correct only on a zero
realized endpoint return. Its frequently zero score is not a balanced binary
classification comparison.

## Archived evidence and diagnosis

The original expanding examples used 480 training sessions initially, 20-session
nonoverlapping horizons, default v1 model/FFT settings and seed 17:

| Archived v1 dataset | Targets / folds | Harmonic MAE | Random-walk MAE | Harmonic RMSE | Random-walk RMSE |
| --- | --- | --- | --- | --- | --- |
| Synthetic research fixture | 240 / 12 | 0.031342 | 0.030998 | 0.039639 | 0.035222 |
| Real Alpaca IEX SPY, 2022–2024 | 260 / 13 | 0.094482 | 0.016978 | 0.100208 | 0.021986 |

V1 lost on both error measures. Direction accuracy was 8/12 versus 0/12 (synthetic)
and 1/13 versus 0/13 (real), under the stated tie rule. The 753 real SPY sessions
were 2022-01-03–2024-12-31. First test: 2023-11-30–2023-12-28; last:
2024-11-13–2024-12-11; thirteen terminal sessions were unscored.

The [original synthetic report](experiments/legacy/synthetic-week2-v1.json) and
private original real report `.local/legacy/spy-week2-v1.json` retain their original
bytes. The [diagnosis artifact](experiments/week2-diagnosis.json), reproduced by
`tools/diagnose_week2_archive.py`, verifies saved predictions/metrics and exposes
per-fold origin gaps. Its post-hoc anchoring/trend ablations reuse archived
coefficients and outcomes. They are development diagnostics, not new model fits or
independent evidence. The trend-only ablation reuses the joint fit's trend
coefficient; it is not a separately fitted baseline. The real report can be
recovered from original `.local/live-week2.json` in the preserved recovery archive;
never replace it with a revised provider download.

Nonaligned analytic signals expose bin-quantization error missed by the original
aligned tests. Correcting it and bootstrap centering is justified by numerical
contracts, not tuning settings until old market results win.

## Corrected reproducibility example and new retrospective evaluation

The [v2 synthetic report](experiments/synthetic-week2-v2.json) uses the same 12-fold,
240-target fixture evaluation and seed 17. Its MAE/RMSE are 0.002882/0.003701 versus
random walk 0.030998/0.035222; direction accuracy is 10/12 versus 0/12. Its input
identity and numerical result reproduced exactly in a second execution. This
reused synthetic dataset is a regression demonstration, not fresh market evidence.

The [2025 SPY protocol](experiments/spy-2025-protocol.json) froze configuration,
package/library identity and runner hash before the first new-data request. It
checked that stored IEX observations ended in 2024, then ingested 2023-01-03 through
2025-12-31. Initial training is 502 sessions through 2024-12-31; expanding evaluation
uses 20-session nonoverlapping folds, default v2 settings and seed 17. Of 250 available
2025 sessions, 240 are scored in 12 folds and ten terminal sessions are unscored.
The first test is 2025-01-02–2025-01-31; last is 2025-11-18–2025-12-16.

| New fixed real evaluation | Harmonic MAE | Random-walk MAE | Harmonic RMSE | Random-walk RMSE |
| --- | --- | --- | --- | --- |
| Alpaca IEX SPY, 2025 targets | 0.021545 | 0.020625 | 0.031729 | 0.028150 |

**The corrected model still lost on both error measures.** Direction accuracy is
6/12 versus 0/12 under the explicit zero-return tie rule. No settings were tuned
after scoring. The [published summary](experiments/spy-2025-summary.json) records
metrics, fold boundaries, hashes and software identity; observed target arrays
remain private in `.local/spy-2025-v2.json` and PostgreSQL. Exact saved-snapshot
replay passed without a provider request, including from the packaged container.
`tools/evaluate_holdout.py verify` checks the retained report/result. The one-time
`freeze`/`run` actions refuse to overwrite an already attempted protocol.

This 2025 interval was new to this evaluation workflow, but is historical and later
adjusted, not a prospective/live trial. One symbol/year cannot establish significance,
generalization or profitability. It is now inspected and must not be reused as an
untouched holdout for later model selection. No forecast-usefulness claim is made.

## Retrieval and strict replay

New envelopes use `analysis-v2`. GET returns the original stored JSON, preserving
legacy `analysis-v1` responses without inserting new model defaults. Strict replay
rejects incompatible schema/model versions with 409 before interpreting a legacy
configuration as v2. For compatible reports, validate saved input integrity,
package/library identity, then recompute solely from the retained snapshot/config
and compare outputs. Changes to latest bars do not rewrite reports. Exact equality
is runtime-specific, not guaranteed across arbitrary toolchain/BLAS changes.


## Week 3 presentation contract

The dashboard displays the existing API's observations, FFT candidates, v2
conditional projections and walk-forward reports. It adds no numerical model or
performance claim. Source labels persist while scrolling; synthetic observations
are explicitly invented examples. Date controls select stored history and the
requested as-of date; the actual exchange-session forecast origin is returned by
the API and shown on the chart. A missing cutoff/range remains a visible error.

The forecast graph uses at most 80 observed sessions for context, then joins the
separate projected curve at the origin. Forecast/band values and heuristic windows
use only returned future session labels. The full selected observation table and
future values remain inspectable. Preprocessing can select detrended log prices
or log returns; regression still targets log adjusted close. All runs record seed
17 and the chosen configuration. The dashboard's shared forecast/backtest horizon
is 1–63 trading sessions to keep their user-selected horizons consistent.

Baseline tables use returned pooled log-price errors and the documented endpoint
sign rule. Any displayed relative RMSE comparison applies only to that selection;
it is not profitability or a generalization test. Repeatedly inspecting/tuning a
backtest window turns it into development data. Saved replay uses the retained
snapshot/configuration and makes no market-provider request. Browser success tests
use the actual offline fixture API, never invented backtest metric responses.

## Sector relative strength — Week 4

The fixed sector universe is XLK (technology), XLF (financials), XLE (energy),
XLI (industrials), XLU (utilities), XLV (health care), XLY (consumer discretionary)
and XLP (consumer staples), benchmarked to SPY. This is a documented subset of US
sectors; it excludes communication services, real estate and materials. It is not
a historical membership or sector-allocation model.

For matching adjusted closes on session `t`, define:

```
RS_i[t] = close_i[t] / close_SPY[t]
q_i[t] = log(close_i[t]) - log(close_SPY[t])
z_i[t] = mean(q_i[t-S+1], ..., q_i[t])
raw_index_i[t] = 100 * exp(q_i[t] - q_i[t0])
smoothed_index_i[t] = 100 * exp(z_i[t] - z_i[t0])
momentum_i[t] = z_i[t] - z_i[t-L]
relative_change_percent_i[t] = 100 * expm1(momentum_i[t])
```

The reference `t0` is the first session in the displayed `lookback_sessions`
window. Default lookback is 126 sessions, `L=20` and `S=5`. The service loads
`lookback + L + S - 1` sessions (150 by default), so every displayed point has a
complete backward smoothing/momentum window. There is no centered smoothing,
future input, interpolation or silent truncation to whatever happens to overlap.
Both indexes start at 100; the smoothed index is normalized to its own reference.
`S=1` recovers the unsmoothed backward log-ratio change in the specification.

The four quadrants use displacement `d=z_i[t]-z_i[t0]` and momentum `m`:

| Condition | State |
| --- | --- |
| `d > 0`, `m > 0` | leading |
| `d < 0`, `m > 0` | improving |
| `d > 0`, `m < 0` | weakening |
| `d < 0`, `m < 0` | lagging |
| `abs(d) <= 1e-12` or `abs(m) <= 1e-12` | neutral |

The boundary rule takes precedence over the other rows. The scatter uses the
smoothed index horizontally (axis 100) and `100*m` vertically (axis 0). This scaled
log change is **not** a percentage return. The table separately shows
`100*expm1(m)`, the relative change of the geometric-mean price ratio over `L`
sessions; it is not the ETF's absolute return. Above 100 can occur while both
sector and benchmark prices decline. Changing the lookback changes the reference
and can change quadrant classifications.

One repeatable-read database transaction loads all nine adjusted-close histories,
restricted to the configured provider/feed, data kind, adjustment basis and exact
XNYS sessions ending at/before `as_of`. A missing sector, benchmark, session or
incompatible source fails explicitly. Numerical code filters to the cutoff before
validation/logs/smoothing. Future append/corruption tests cover all outputs.
Sector reports retain selected inputs, versions, per-symbol ingestion IDs, hash,
window configuration, rule version and software identity. Re-ingestion may update
latest bars; saved reports and their snapshots retain their original observations.

Sector fixtures are separate from the unchanged stock research file. For sector
index `i=0..7` and the same 720 benchmark sessions:

```
ratio[t] = (0.6 + 0.07*i) * exp(0.06*sin(2*pi*t/160 + i*pi/4))
close_i[t] = round(SPY_synthetic_close[t] * ratio[t], 8)
```

OHLC and constant volumes are invented, deterministically generated and labeled
synthetic. Fixture version is `synthetic-sectors-v1`; the research provider ID
remains `synthetic-research-v1` and reports include the individual file versions.
The current [full synthetic experiment](experiments/synthetic-mvp-week4.json)
records 126 observations for each sector and replays exactly with the locked runtime.

These are observed, descriptive heuristics. They establish no sector forecast,
rotation persistence, economic law, significance or investment recommendation.
Historical adjusted inputs can reflect later revisions; no point-in-time guarantee
or historical index-membership claim is made.

## Software identity after Week 4

Version 0.4.0 adds sector/domain/API files; package-wide source hashes and the
recorded package version therefore change. The original Week 2 forecast algorithms,
protocols and negative reports remain unchanged. Strict replay deliberately returns
409 when the current package/library identity differs, even when the numerical
algorithm happens to be identical. GET returns original historical JSON.

The preserved Week 3 checkout with its own locked 0.2.1 runtime successfully
verified the frozen 2025 protocol, report hash and retained-snapshot replay after
the Week 4 ingestion. See [recovery](RECOVERY.md). Under the current runtime, the
older synthetic reference still reproduces the same numerical inputs/results via
`tools/run_demo.py --verify`; new Week 4 runs verify strict replay under their own
identity. Do not overwrite a historical report to make a new code hash match it.
