/** Chart inputs preserve backend session dates; no calendar interpolation is used. */
export interface PriceChartPoint {
  session_date: string;
  close: number;
}

export interface SpectrumChartPoint {
  period_sessions: number;
  power: number;
}

export interface ForecastChartPoint {
  session_date: string;
  value: number;
  lower: number;
  upper: number;
}

export interface ForecastTurningWindow {
  kind: "peak" | "trough";
  window_start: string;
  window_end: string;
}

export interface ForecastPlotPoint {
  session_date: string;
  observed?: number;
  projected?: number;
  uncertaintyRange?: [number, number];
}

export function isSessionDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function isPositiveFinite(value: number): boolean {
  return Number.isFinite(value) && value > 0;
}

export function preparePriceData(points: readonly PriceChartPoint[]): PriceChartPoint[] {
  const sessions = new Set<string>();
  return points
    .filter((point) => {
      if (
        !isSessionDate(point.session_date) ||
        !isPositiveFinite(point.close) ||
        sessions.has(point.session_date)
      ) {
        return false;
      }
      sessions.add(point.session_date);
      return true;
    })
    .map((point) => ({ session_date: point.session_date, close: point.close }))
    .sort((left, right) => left.session_date.localeCompare(right.session_date));
}

export function prepareSpectrumData(points: readonly SpectrumChartPoint[]): SpectrumChartPoint[] {
  return points
    .filter(
      (point) =>
        isPositiveFinite(point.period_sessions) && Number.isFinite(point.power) && point.power >= 0,
    )
    .map((point) => ({ period_sessions: point.period_sessions, power: point.power }))
    .sort((left, right) => left.period_sessions - right.period_sessions);
}

/**
 * Join the projected curve at the actual origin observation. Only provided
 * exchange-session labels are retained, and observed bars after the cutoff are
 * excluded even when a caller supplies a wider historical date range.
 */
export function buildForecastChartData(
  history: readonly PriceChartPoint[],
  points: readonly ForecastChartPoint[],
  asOf: string,
  historyLimit = 80,
): ForecastPlotPoint[] {
  if (!isSessionDate(asOf)) return [];
  const limit = Number.isInteger(historyLimit) && historyLimit > 0 ? historyLimit : 80;
  const observed = preparePriceData(history)
    .filter((point) => point.session_date <= asOf)
    .slice(-limit);
  const futureSessions = new Set<string>();
  const future = points
    .filter((point) => {
      if (
        !isSessionDate(point.session_date) ||
        point.session_date <= asOf ||
        !isPositiveFinite(point.value) ||
        !isPositiveFinite(point.lower) ||
        !isPositiveFinite(point.upper) ||
        point.lower > point.upper ||
        futureSessions.has(point.session_date)
      ) {
        return false;
      }
      futureSessions.add(point.session_date);
      return true;
    })
    .sort((left, right) => left.session_date.localeCompare(right.session_date));

  const data: ForecastPlotPoint[] = observed.map((point) => ({
    session_date: point.session_date,
    observed: point.close,
    ...(point.session_date === asOf
      ? { projected: point.close, uncertaintyRange: [point.close, point.close] as [number, number] }
      : {}),
  }));
  for (const point of future) {
    data.push({
      session_date: point.session_date,
      projected: point.value,
      uncertaintyRange: [point.lower, point.upper],
    });
  }
  return data;
}

export function visibleTurningWindows(
  windows: readonly ForecastTurningWindow[],
  data: readonly ForecastPlotPoint[],
  asOf: string,
): ForecastTurningWindow[] {
  const sessions = new Set(data.map((point) => point.session_date));
  return windows.filter(
    (window) =>
      window.window_start > asOf &&
      window.window_start <= window.window_end &&
      sessions.has(window.window_start) &&
      sessions.has(window.window_end),
  );
}
