import { describe, expect, it } from "vitest";
import {
  buildForecastChartData,
  isSessionDate,
  prepareSpectrumData,
  visibleTurningWindows,
} from "./data";

describe("chart financial labels and cutoff isolation", () => {
  it("joins at the observation and omits hindsight prices after the cutoff", () => {
    const history = [
      { session_date: "2024-01-12", close: 100 },
      { session_date: "2024-01-16", close: 999 },
    ];
    const future = [{ session_date: "2024-01-16", value: 101, lower: 98, upper: 104 }];
    const points = buildForecastChartData(history, future, "2024-01-12");
    expect(points).toEqual([
      { session_date: "2024-01-12", observed: 100, projected: 100, uncertaintyRange: [100, 100] },
      { session_date: "2024-01-16", projected: 101, uncertaintyRange: [98, 104] },
    ]);
    // No weekend, holiday, interpolated price, or future observation is invented.
    expect(points).toHaveLength(2);
  });

  it("keeps zero spectral power and rejects nonfinite or nonsensical periods", () => {
    expect(
      prepareSpectrumData([
        { period_sessions: 40, power: 0 },
        { period_sessions: 120, power: 1 },
        { period_sessions: 0, power: 8 },
        { period_sessions: 10, power: NaN },
      ]),
    ).toEqual([
      { period_sessions: 40, power: 0 },
      { period_sessions: 120, power: 1 },
    ]);
  });

  it("does not extend heuristic windows beyond supplied future sessions", () => {
    const data = [{ session_date: "2024-01-16", projected: 101 }];
    expect(
      visibleTurningWindows(
        [
          { kind: "peak", window_start: "2024-01-12", window_end: "2024-01-16" },
          { kind: "trough", window_start: "2024-01-16", window_end: "2024-01-18" },
        ],
        data,
        "2024-01-12",
      ),
    ).toEqual([]);
  });

  it("validates actual ISO calendar dates without local timezone shifts", () => {
    expect(isSessionDate("2024-02-29")).toBe(true);
    expect(isSessionDate("2025-02-29")).toBe(false);
    expect(isSessionDate("2025-13-01")).toBe(false);
  });
});
