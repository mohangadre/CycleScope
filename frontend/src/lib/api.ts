import type {
  AnalysisResponse,
  BacktestAnalysis,
  CycleAnalysis,
  FFTConfig,
  ForecastAnalysis,
  ForecastResult,
  PriceHistory,
  PricesResponse,
  SymbolsResponse,
  TypedAnalysis,
  SectorResponse,
} from "./api-types";

export type * from "./api-types";

const MAX_HISTORY_SESSIONS = 2520;
const PAGE_SIZE = 1000;
const SYMBOL = /^[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,4})?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number,
    public readonly requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface PricesQuery {
  ticker: string;
  start: string;
  end: string;
}

export interface FFTOptions {
  input?: FFTConfig["input"];
  detrend?: FFTConfig["detrend"];
  window?: FFTConfig["window"];
}

export interface CycleQuery extends FFTOptions {
  ticker: string;
  asOf: string;
  lookback: number;
}

export interface ForecastQuery extends CycleQuery {
  horizonSessions: number;
}

export interface BacktestQuery extends PricesQuery, FFTOptions {
  initialTrainSessions: number;
  horizonSessions: number;
  mode?: "expanding" | "rolling";
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function invalidResponse(message = "The API returned an invalid response."): never {
  throw new ApiError(message, "invalid_response", 502);
}

function finiteJson(value: unknown): void {
  if (typeof value === "number" && !Number.isFinite(value)) invalidResponse();
  if (Array.isArray(value)) value.forEach(finiteJson);
  else if (record(value)) Object.values(value).forEach(finiteJson);
}

function dateString(value: unknown): value is string {
  return typeof value === "string" && ISO_DATE.test(value);
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function positive(value: unknown): value is number {
  return finite(value) && value > 0;
}

function integer(value: unknown): value is number {
  return finite(value) && Number.isInteger(value) && value >= 0;
}

function source(value: unknown): boolean {
  return (
    record(value) &&
    typeof value.provider === "string" &&
    (value.data_kind === "real" || value.data_kind === "synthetic") &&
    value.adjustment_basis === "split_dividend_adjusted"
  );
}

function validatePrices(value: unknown): asserts value is PricesResponse {
  if (
    !source(value) ||
    !record(value) ||
    typeof value.ticker !== "string" ||
    value.currency !== "USD" ||
    value.calendar !== "XNYS" ||
    value.date_basis !== "exchange_session" ||
    value.price_unit !== "USD_per_share" ||
    !record(value.requested_range) ||
    !dateString(value.requested_range.start) ||
    !dateString(value.requested_range.end) ||
    !integer(value.total) ||
    !integer(value.limit) ||
    !integer(value.offset) ||
    typeof value.has_more !== "boolean" ||
    !Array.isArray(value.warnings) ||
    !value.warnings.every((warning) => typeof warning === "string") ||
    !Array.isArray(value.bars)
  ) {
    invalidResponse();
  }
  for (const bar of value.bars) {
    if (
      !record(bar) ||
      bar.symbol !== value.ticker ||
      !dateString(bar.session_date) ||
      typeof bar.close !== "string" ||
      !positive(Number(bar.close))
    ) {
      invalidResponse("The API returned an invalid adjusted price.");
    }
  }
}

function validateForecast(value: unknown): asserts value is ForecastResult {
  if (
    !record(value) ||
    !dateString(value.as_of) ||
    !dateString(value.forecast_origin) ||
    !dateString(value.train_start) ||
    !dateString(value.train_end) ||
    value.forecast_origin > value.as_of ||
    value.train_end !== value.forecast_origin ||
    !positive(value.last_observed_price) ||
    !integer(value.training_sample_count) ||
    !integer(value.horizon_sessions) ||
    !record(value.config) ||
    !record(value.fit) ||
    !record(value.uncertainty) ||
    !Array.isArray(value.points) ||
    value.points.length !== value.horizon_sessions ||
    !Array.isArray(value.turning_points) ||
    !Array.isArray(value.warnings)
  ) {
    invalidResponse();
  }
  let previousDate = value.forecast_origin;
  for (const [index, point] of value.points.entries()) {
    if (
      !record(point) ||
      point.session_offset !== index + 1 ||
      !dateString(point.session_date) ||
      point.session_date <= previousDate ||
      !positive(point.value) ||
      !positive(point.lower) ||
      !positive(point.upper) ||
      point.lower > point.upper
    ) {
      invalidResponse("The API returned invalid future forecast sessions or bounds.");
    }
    previousDate = point.session_date;
  }
}

function validateMetrics(value: unknown): boolean {
  return (
    record(value) &&
    value.target === "log_adjusted_close" &&
    value.error_unit === "natural_log_price" &&
    finite(value.mae) &&
    value.mae >= 0 &&
    finite(value.rmse) &&
    value.rmse >= 0 &&
    finite(value.directional_accuracy) &&
    value.directional_accuracy >= 0 &&
    value.directional_accuracy <= 1 &&
    integer(value.error_count) &&
    integer(value.direction_count)
  );
}

function validateAnalysis(value: unknown): asserts value is TypedAnalysis {
  if (
    !record(value) ||
    (value.schema_version !== "analysis-v1" && value.schema_version !== "analysis-v2") ||
    typeof value.run_id !== "string" ||
    typeof value.created_at !== "string" ||
    !source(value.source) ||
    !record(value.source) ||
    typeof value.source.ticker !== "string" ||
    !record(value.software) ||
    !record(value.result)
  ) {
    invalidResponse();
  }
  const result = value.result;
  if (value.kind === "forecast") {
    validateForecast(result);
  } else if (value.kind === "cycles") {
    if (
      !dateString(result.as_of) ||
      !dateString(result.forecast_origin) ||
      !record(result.config) ||
      !record(result.analysis) ||
      !Array.isArray(result.analysis.cycles) ||
      !Array.isArray(result.analysis.spectrum)
    )
      invalidResponse();
    for (const point of [...result.analysis.cycles, ...result.analysis.spectrum]) {
      if (
        !record(point) ||
        !positive(point.period_sessions) ||
        !positive(point.frequency) ||
        !finite(point.power) ||
        point.power < 0
      )
        invalidResponse();
    }
  } else if (value.kind === "backtest") {
    if (
      !record(result.config) ||
      !Array.isArray(result.folds) ||
      !integer(result.fold_count) ||
      result.folds.length !== result.fold_count ||
      !validateMetrics(result.harmonic_metrics) ||
      !validateMetrics(result.baseline_metrics)
    )
      invalidResponse();
    for (const fold of result.folds) {
      if (!record(fold)) invalidResponse();
      validateForecast(fold.forecast);
    }
  } else {
    invalidResponse();
  }
}

function validateSectors(value: unknown): asserts value is SectorResponse {
  if (
    !record(value) ||
    value.schema_version !== "sectors-v1" ||
    !source(value) ||
    value.currency !== "USD" ||
    typeof value.run_id !== "string" ||
    typeof value.input_hash !== "string" ||
    !record(value.result) ||
    value.result.benchmark !== "SPY" ||
    value.result.observation_kind !== "observed_relative_performance" ||
    value.result.model_version !== "sector-relative-strength-v1" ||
    value.result.momentum_unit !== "natural_log_relative_strength_change" ||
    !record(value.result.config) ||
    !integer(value.result.config.lookback_sessions) ||
    !dateString(value.result.observed_through) ||
    !dateString(value.result.as_of) ||
    !dateString(value.result.normalization_session) ||
    value.result.observed_through > value.result.as_of ||
    !Array.isArray(value.result.sectors) ||
    value.result.sectors.length !== 8
  )
    invalidResponse("Invalid sector report.");
  const expected = new Set(["XLK", "XLF", "XLE", "XLI", "XLU", "XLV", "XLY", "XLP"]);
  const quadrants = ["leading", "improving", "weakening", "lagging", "neutral"];
  let commonDates: string[] | undefined;
  for (const sector of value.result.sectors) {
    if (
      !record(sector) ||
      typeof sector.ticker !== "string" ||
      !expected.delete(sector.ticker) ||
      typeof sector.name !== "string" ||
      !Array.isArray(sector.points) ||
      sector.points.length !== value.result.config.lookback_sessions
    )
      invalidResponse("Sector coverage is incomplete.");
    let previous = "";
    for (const [index, point] of sector.points.entries()) {
      if (
        !record(point) ||
        !dateString(point.session_date) ||
        point.session_date <= previous ||
        point.session_date > value.result.observed_through ||
        !positive(point.relative_strength) ||
        !positive(point.normalized_rs) ||
        !positive(point.smoothed_normalized_rs) ||
        !finite(point.momentum_log_rs) ||
        !finite(point.relative_change_percent) ||
        !quadrants.includes(String(point.quadrant))
      )
        invalidResponse("Invalid relative strength observations.");
      if (
        (commonDates && point.session_date !== commonDates[index]) ||
        (index === 0 &&
          (point.session_date !== value.result.normalization_session ||
            point.normalized_rs !== 100 ||
            point.smoothed_normalized_rs !== 100))
      )
        invalidResponse("Sector sessions or normalization references do not match.");
      previous = point.session_date;
    }
    if (previous !== value.result.observed_through)
      invalidResponse("Sector cutoff does not match its observations.");
    commonDates ??= sector.points.map((point) => point.session_date);
  }
}

function tickerPath(ticker: string): string {
  if (!SYMBOL.test(ticker)) {
    throw new ApiError("Enter a valid uppercase ticker, such as SPY.", "invalid_ticker", 422);
  }
  return encodeURIComponent(ticker);
}

function fftConfig(query: FFTOptions) {
  return {
    input: query.input ?? "detrended_log_adjusted_close",
    detrend: query.detrend ?? "linear",
    window: query.window ?? "hann",
  };
}

/** All browser requests use the same-origin, fixed-destination Next.js proxy. */
export class ApiClient {
  constructor(private readonly fetcher: typeof fetch = (...args) => fetch(...args)) {}

  private async request(path: string, init: RequestInit = {}): Promise<unknown> {
    let response: Response;
    try {
      response = await this.fetcher(`/backend${path}`, {
        ...init,
        cache: "no-store",
        headers: { Accept: "application/json", ...init.headers },
      });
    } catch (error) {
      if (init.signal?.aborted || (error instanceof Error && error.name === "AbortError")) {
        throw error;
      }
      throw new ApiError(
        "Cannot reach the API. Check that the backend is running.",
        "network_unavailable",
        0,
      );
    }
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new ApiError(
        response.ok
          ? "The API returned invalid JSON."
          : `The API request failed (${response.status}).`,
        response.ok ? "invalid_response" : "http_error",
        response.ok ? 502 : response.status,
        response.headers.get("X-Request-ID"),
      );
    }
    if (!response.ok) {
      const detail = record(payload) && record(payload.error) ? payload.error : null;
      throw new ApiError(
        typeof detail?.message === "string"
          ? detail.message
          : `The API request failed (${response.status}).`,
        typeof detail?.code === "string" ? detail.code : "http_error",
        response.status,
        typeof detail?.request_id === "string"
          ? detail.request_id
          : response.headers.get("X-Request-ID"),
      );
    }
    finiteJson(payload);
    return payload;
  }

  async getSymbols(signal?: AbortSignal): Promise<SymbolsResponse> {
    const payload = await this.request("/api/v1/symbols", { signal });
    if (
      !record(payload) ||
      typeof payload.provider !== "string" ||
      (payload.data_kind !== "synthetic" && payload.data_kind !== "real") ||
      !Array.isArray(payload.instruments) ||
      !payload.instruments.every(
        (item) =>
          record(item) && typeof item.symbol === "string" && typeof item.display_name === "string",
      )
    )
      invalidResponse();
    return payload as SymbolsResponse;
  }

  async getSectorRotation(
    query: {
      asOf: string;
      lookbackSessions: number;
      momentumSessions: number;
      smoothingSessions: number;
    },
    signal?: AbortSignal,
  ): Promise<SectorResponse> {
    const params = new URLSearchParams({
      as_of: query.asOf,
      lookback_sessions: String(query.lookbackSessions),
      momentum_sessions: String(query.momentumSessions),
      smoothing_sessions: String(query.smoothingSessions),
    });
    const body = await this.request(`/api/v1/sectors/rotation?${params}`, { signal });
    validateSectors(body);
    return body;
  }

  async replaySector(runId: string, signal?: AbortSignal): Promise<SectorResponse> {
    const body = await this.request(`/api/v1/sectors/runs/${encodeURIComponent(runId)}/replay`, {
      method: "POST",
      signal,
    });
    validateSectors(body);
    return body;
  }

  async getPrices(query: PricesQuery, signal?: AbortSignal): Promise<PriceHistory> {
    const path = tickerPath(query.ticker);
    const bars: PricesResponse["bars"] = [];
    let first: PricesResponse | undefined;
    let pageCount = 0;
    do {
      const parameters = new URLSearchParams({
        start: query.start,
        end: query.end,
        limit: String(PAGE_SIZE),
        offset: String(bars.length),
      });
      const payload = await this.request(`/api/v1/prices/${path}?${parameters}`, { signal });
      validatePrices(payload);
      pageCount += 1;
      if (payload.total > MAX_HISTORY_SESSIONS) {
        throw new ApiError(
          "Select a shorter range: the dashboard supports at most 2,520 stored sessions.",
          "history_range_too_large",
          422,
        );
      }
      if (
        payload.ticker !== query.ticker ||
        payload.requested_range.start !== query.start ||
        payload.requested_range.end !== query.end ||
        payload.offset !== bars.length ||
        payload.bars.length > PAGE_SIZE ||
        payload.bars.length + bars.length > payload.total ||
        payload.has_more !== payload.offset + payload.bars.length < payload.total ||
        (payload.has_more && payload.bars.length === 0)
      )
        invalidResponse("Price pagination was inconsistent. Reload the range.");
      if (
        first &&
        (payload.total !== first.total ||
          payload.provider !== first.provider ||
          payload.data_kind !== first.data_kind ||
          payload.adjustment_basis !== first.adjustment_basis ||
          payload.currency !== first.currency ||
          payload.calendar !== first.calendar)
      )
        invalidResponse("Price data changed while loading. Reload the range.");
      first ??= payload;
      for (const bar of payload.bars) {
        const previous = bars.at(-1);
        if (
          bar.session_date < query.start ||
          bar.session_date > query.end ||
          (previous && previous.session_date >= bar.session_date)
        )
          invalidResponse(
            "Price sessions were duplicated, out of order, or outside the requested range.",
          );
        bars.push(bar);
      }
      if (!payload.has_more) break;
    } while (bars.length <= MAX_HISTORY_SESSIONS);
    if (!first) invalidResponse();
    return {
      ticker: first.ticker,
      provider: first.provider,
      data_kind: first.data_kind,
      adjustment_basis: first.adjustment_basis,
      currency: first.currency,
      date_basis: first.date_basis,
      calendar: first.calendar,
      price_unit: first.price_unit,
      volume_unit: first.volume_unit,
      requested_range: first.requested_range,
      total: first.total,
      warnings: first.warnings,
      bars,
      page_count: pageCount,
    };
  }

  async getCycles(query: CycleQuery, signal?: AbortSignal): Promise<CycleAnalysis> {
    const parameters = new URLSearchParams({
      as_of: query.asOf,
      lookback: String(query.lookback),
      ...fftConfig(query),
    });
    const payload = await this.request(`/api/v1/cycles/${tickerPath(query.ticker)}?${parameters}`, {
      signal,
    });
    validateAnalysis(payload);
    if (payload.kind !== "cycles") invalidResponse();
    return payload;
  }

  async getForecast(query: ForecastQuery, signal?: AbortSignal): Promise<ForecastAnalysis> {
    const payload = await this.request(`/api/v1/forecasts/${tickerPath(query.ticker)}`, {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        as_of: query.asOf,
        lookback: query.lookback,
        horizon_sessions: query.horizonSessions,
        model: { seed: 17, fft: fftConfig(query) },
      }),
    });
    validateAnalysis(payload);
    if (payload.kind !== "forecast") invalidResponse();
    return payload;
  }

  async runBacktest(query: BacktestQuery, signal?: AbortSignal): Promise<BacktestAnalysis> {
    tickerPath(query.ticker);
    const payload = await this.request("/api/v1/backtests", {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker: query.ticker,
        start: query.start,
        end: query.end,
        evaluation: {
          initial_train_sessions: query.initialTrainSessions,
          horizon_sessions: query.horizonSessions,
          step_sessions: query.horizonSessions,
          mode: query.mode ?? "expanding",
          model: { seed: 17, fft: fftConfig(query) },
        },
      }),
    });
    validateAnalysis(payload);
    if (payload.kind !== "backtest") invalidResponse();
    return payload;
  }

  async getAnalysis(runId: string, signal?: AbortSignal): Promise<TypedAnalysis> {
    const payload = await this.request(`/api/v1/analyses/${encodeURIComponent(runId)}`, { signal });
    validateAnalysis(payload);
    return payload;
  }

  async getBacktest(runId: string, signal?: AbortSignal): Promise<BacktestAnalysis> {
    const payload = await this.request(`/api/v1/backtests/${encodeURIComponent(runId)}`, {
      signal,
    });
    validateAnalysis(payload);
    if (payload.kind !== "backtest") invalidResponse();
    return payload;
  }

  async replayBacktest(runId: string, signal?: AbortSignal): Promise<BacktestAnalysis> {
    const payload = await this.request(`/api/v1/backtests/${encodeURIComponent(runId)}/replay`, {
      method: "POST",
      signal,
    });
    validateAnalysis(payload);
    if (payload.kind !== "backtest") invalidResponse();
    return payload;
  }
}

export const api = new ApiClient();

// Kept as an export for consumers that only need the generated transport envelope.
export type { AnalysisResponse };
