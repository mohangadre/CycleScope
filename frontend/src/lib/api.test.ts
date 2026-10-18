import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "./api";

function prices(offset = 0, total = 1) {
  return {
    ticker: "SPY",
    provider: "synthetic-test",
    data_kind: "synthetic",
    adjustment_basis: "split_dividend_adjusted",
    currency: "USD",
    calendar: "XNYS",
    date_basis: "exchange_session",
    price_unit: "USD_per_share",
    volume_unit: "shares",
    requested_range: { start: "2020-01-01", end: "2024-12-31" },
    total,
    offset,
    limit: 1000,
    has_more: offset + Math.min(1000, total - offset) < total,
    warnings: [],
    // Deliberate dummy observations exercise transport pagination, never analytics.
    bars: Array.from({ length: Math.min(1000, total - offset) }, (_, index) => ({
      symbol: "SPY",
      session_date: new Date(Date.UTC(2020, 0, 1 + offset + index)).toISOString().slice(0, 10),
      close: "100.00000000",
    })),
  };
}
const query = { ticker: "SPY", start: "2020-01-01", end: "2024-12-31" };
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("same-origin typed API boundary", () => {
  it("validates source-specific empty coverage and rejects inconsistent bounds", async () => {
    const coverage = {
      ticker: "SPY",
      provider: "alpaca-iex",
      data_kind: "real",
      adjustment_basis: "split_dividend_adjusted",
      session_count: 0,
      first_session: null,
      last_session: null,
      last_ingested_at: null,
      latest_completed_session: "2024-03-28",
    };
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response(coverage))
      .mockResolvedValueOnce(response({ ...coverage, session_count: 10 }));
    expect(await new ApiClient(fetcher).getPriceCoverage("SPY")).toEqual(coverage);
    await expect(new ApiClient(fetcher).getPriceCoverage("SPY")).rejects.toThrow(
      "Invalid stored price coverage",
    );
  });

  it("requires real download provenance matching the requested ticker and range", async () => {
    const body = {
      ticker: "SPY",
      provider: "alpaca-iex",
      data_kind: "real",
      requested_range: { start: query.start, end: query.end },
      ingestion_run_id: "test-audit-id",
      coverage: {
        ticker: "SPY",
        provider: "alpaca-sip",
        data_kind: "real",
        adjustment_basis: "split_dividend_adjusted",
        session_count: 1,
        first_session: "2024-03-28",
        last_session: "2024-03-28",
        last_ingested_at: "2024-03-29T00:00:00Z",
        latest_completed_session: "2024-03-28",
      },
    };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response(body));
    await expect(new ApiClient(fetcher).refreshPrices(query)).rejects.toThrow(
      "Downloaded price source does not match",
    );
    expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).toEqual({
      start: query.start,
      end: query.end,
    });
  });
  it("loads every page without dropping the 1001st observation", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response(prices(0, 1001)))
      .mockResolvedValueOnce(response(prices(1000, 1001)));
    const result = await new ApiClient(fetcher).getPrices(query);
    expect(result.bars).toHaveLength(1001);
    expect(result.total).toBe(1001);
    expect(result.page_count).toBe(2);
    expect(fetcher.mock.calls[1][0]).toContain("offset=1000");
    expect(fetcher.mock.calls.every(([url]) => String(url).startsWith("/backend/"))).toBe(true);
  });

  it("rejects a provider change midway through pagination", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response(prices(0, 1001)))
      .mockResolvedValueOnce(response({ ...prices(1000, 1001), provider: "other-feed" }));
    await expect(new ApiClient(fetcher).getPrices(query)).rejects.toThrow("changed while loading");
  });

  it("bounds history before making more requests", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response(prices(0, 2521)));
    await expect(new ApiClient(fetcher).getPrices(query)).rejects.toThrow("2,520");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("rejects duplicate sessions and nonpositive prices", async () => {
    const duplicate = prices(0, 2);
    duplicate.bars[1].session_date = duplicate.bars[0].session_date;
    await expect(
      new ApiClient(vi.fn<typeof fetch>().mockResolvedValue(response(duplicate))).getPrices(query),
    ).rejects.toThrow("duplicated");
    const invalid = prices();
    invalid.bars[0].close = "0";
    await expect(
      new ApiClient(vi.fn<typeof fetch>().mockResolvedValue(response(invalid))).getPrices(query),
    ).rejects.toThrow("invalid adjusted price");
  });

  it("preserves structured errors and request IDs without fallback", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      response(
        {
          error: {
            code: "provider_unavailable",
            message: "No configured data",
            request_id: "known-request",
          },
        },
        503,
      ),
    );
    await expect(new ApiClient(fetcher).getPrices(query)).rejects.toMatchObject({
      code: "provider_unavailable",
      status: 503,
      message: "No configured data",
      requestId: "known-request",
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("passes cancellation through without converting it to a provider error", async () => {
    const controller = new AbortController();
    controller.abort();
    const aborted = new DOMException("Cancelled", "AbortError");
    const fetcher = vi.fn<typeof fetch>().mockRejectedValue(aborted);
    await expect(new ApiClient(fetcher).getPrices(query, controller.signal)).rejects.toBe(aborted);
    expect(fetcher.mock.calls[0][1]?.signal).toBe(controller.signal);
  });

  it("rejects invalid tickers before fetching", async () => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(
      new ApiClient(fetcher).getPrices({ ...query, ticker: "../../secret" }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("validates future-only dates against an actual versioned forecast", async () => {
    const reference = JSON.parse(
      readFileSync("../docs/experiments/synthetic-week2-v2.json", "utf8"),
    );
    const forecast = {
      ...reference,
      kind: "forecast",
      result: structuredClone(reference.result.folds[0].forecast),
    };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(response(forecast));
    const client = new ApiClient(fetcher);
    const request = {
      ticker: "SPY",
      asOf: forecast.result.as_of,
      lookback: 480,
      horizonSessions: 20,
      input: "log_returns" as const,
      window: "boxcar" as const,
    };
    const actual = await client.getForecast(request);
    expect(actual.result.points).toHaveLength(20);
    expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body)).model).toMatchObject({
      seed: 17,
      fft: { input: "log_returns", window: "boxcar" },
    });
    forecast.result.points[0].session_date = forecast.result.forecast_origin;
    fetcher.mockResolvedValueOnce(response(forecast));
    await expect(client.getForecast(request)).rejects.toThrow("invalid future forecast");
  });
});
