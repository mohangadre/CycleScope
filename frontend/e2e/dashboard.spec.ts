import { expect, test, type Page } from "@playwright/test";

const fixture = { start: "2020-01-02", end: "2022-11-08" };

async function configureFixture(page: Page, ticker = "SPY") {
  await page.goto("/");
  await expect(page.getByRole("combobox", { name: "Ticker", exact: true })).toBeEnabled();
  await page.getByRole("combobox", { name: "Ticker", exact: true }).selectOption(ticker);
  await page.getByLabel("Start date", { exact: true }).fill(fixture.start);
  await page.getByLabel("End date", { exact: true }).fill(fixture.end);
  await page.getByLabel("Lookback (trading sessions)", { exact: true }).fill("480");
  await page.getByLabel("Forecast horizon (trading sessions)", { exact: true }).fill("20");
  await page.getByLabel("Initial training (trading sessions)", { exact: true }).fill("480");
}

function endpoint(path: string) {
  return (response: { url(): string }) => new URL(response.url()).pathname === `/backend${path}`;
}

function errorBody(code: string, message: string) {
  return { error: { code, message, request_id: "e2e-visible-request" } };
}

test("fixture journey displays stored observations, cycles, forecast and matching baseline evaluation", async ({
  page,
}) => {
  // Only checked-in synthetic observations from the isolated API are used here.
  // None of the successful financial results are intercepted or invented.
  await configureFixture(page);
  const responses = Promise.all([
    page.waitForResponse(endpoint("/api/v1/prices/SPY")),
    page.waitForResponse(endpoint("/api/v1/cycles/SPY")),
    page.waitForResponse(endpoint("/api/v1/forecasts/SPY")),
  ]);
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  const [pricesResponse, cyclesResponse, forecastResponse] = await responses;
  for (const response of [pricesResponse, cyclesResponse, forecastResponse]) {
    expect(response.ok(), `HTTP ${response.status()} from ${response.url()}`).toBeTruthy();
  }
  const prices = (await pricesResponse.json()) as { total: number; data_kind: string };
  const cycles = (await cyclesResponse.json()) as {
    result: { analysis: { cycles: { period_sessions: number; significance_status: string }[] } };
  };
  const forecast = (await forecastResponse.json()) as {
    result: {
      horizon_sessions: number;
      uncertainty: { calibrated: boolean };
      forecast_origin: string;
    };
  };
  expect(prices.total).toBe(720);
  expect(prices.data_kind).toBe("synthetic");
  expect(cycles.result.analysis.cycles.length).toBeGreaterThan(0);
  expect(
    cycles.result.analysis.cycles.every((cycle) => cycle.significance_status === "not_tested"),
  ).toBeTruthy();
  expect(forecast.result.horizon_sessions).toBe(20);
  expect(forecast.result.uncertainty.calibrated).toBe(false);

  const analysis = page.getByTestId("analysis-results");
  await expect(analysis).toBeVisible();
  for (const name of ["Price history", "Candidate cycles", "Forecast"]) {
    await expect(analysis.getByRole("heading", { name, exact: true })).toBeVisible();
  }
  await expect(page.getByText(/SYNTHETIC DATA/).first()).toBeVisible();
  await expect(analysis.getByText(/observed/i).first()).toBeVisible();
  await expect(analysis.getByText(/projected/i).first()).toBeVisible();
  await expect(analysis.getByText(/cutoff/i).first()).toBeVisible();
  await expect(analysis.getByText(/uncalibrated/i).first()).toBeVisible();
  await expect(analysis.getByText(/not tested/i).first()).toBeVisible();
  const periods = analysis.getByRole("table", { name: "Candidate cycle periods", exact: true });
  await expect(periods).toBeVisible();
  await expect(analysis.locator(".recharts-surface")).toHaveCount(3);
  const firstPeriod = cycles.result.analysis.cycles[0]!.period_sessions;
  const periodText = await periods.getByRole("row").nth(1).getByRole("cell").first().textContent();
  expect(Number.parseFloat(periodText ?? "NaN")).toBeCloseTo(firstPeriod, 1);

  const backtestResponsePromise = page.waitForResponse(endpoint("/api/v1/backtests"));
  await page.getByRole("button", { name: "Run backtest", exact: true }).click();
  const backtestResponse = await backtestResponsePromise;
  expect(backtestResponse.ok(), await backtestResponse.text()).toBeTruthy();
  const backtest = (await backtestResponse.json()) as {
    result: {
      fold_count: number;
      evaluated_forecast_count: number;
      harmonic_metrics: { rmse: number; error_count: number };
      baseline_metrics: { rmse: number; error_count: number };
    };
  };
  expect(backtest.result.fold_count).toBe(12);
  expect(backtest.result.evaluated_forecast_count).toBe(240);
  expect(backtest.result.harmonic_metrics.error_count).toBe(240);
  expect(backtest.result.baseline_metrics.error_count).toBe(240);

  const results = page.getByTestId("backtest-results");
  await expect(
    results.getByRole("heading", { name: "Backtest comparison", exact: true }),
  ).toBeVisible();
  await expect(results.getByText("12 folds", { exact: true })).toBeVisible();
  await expect(results.getByText(/240.*targets/)).toBeVisible();
  const metrics = results.getByRole("table", { name: "Backtest metrics", exact: true });
  await expect(metrics.getByRole("row", { name: /Harmonic/i })).toBeVisible();
  await expect(metrics.getByRole("row", { name: /Random walk/i })).toBeVisible();
  const harmonicCells = metrics.getByRole("row", { name: /Harmonic/i }).getByRole("cell");
  const baselineCells = metrics.getByRole("row", { name: /Random walk/i }).getByRole("cell");
  expect(Number(await harmonicCells.nth(2).textContent())).toBeCloseTo(
    backtest.result.harmonic_metrics.rmse,
    5,
  );
  expect(Number(await baselineCells.nth(2).textContent())).toBeCloseTo(
    backtest.result.baseline_metrics.rmse,
    5,
  );
  await expect(results.getByText(/log.*price/i).first()).toBeVisible();
  await expect(
    results.getByRole("table", { name: "Walk-forward folds", exact: true }).getByRole("row"),
  ).toHaveCount(13);
  await results.getByRole("button", { name: "Replay saved report", exact: true }).click();
  await expect(results.getByRole("status")).toContainText("Exact replay verified");
  await page.locator(".controls-panel").evaluate((element) => {
    element.scrollTop = 0;
  });
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({ path: test.info().outputPath("dashboard-desktop.png"), fullPage: true });
});

test("loading is visible and changing the ticker cancels stale work", async ({ page }) => {
  await configureFixture(page);
  const priceResponse = await page.request.get(
    `/backend/api/v1/prices/SPY?start=${fixture.start}&end=${fixture.end}&limit=1000`,
  );
  expect(priceResponse.ok()).toBeTruthy();
  const priceBody: unknown = await priceResponse.json();
  let release = () => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let markStarted = () => {};
  const started = new Promise<void>((resolve) => {
    markStarted = resolve;
  });
  await page.route("**/backend/api/v1/prices/SPY?*", async (route) => {
    markStarted();
    await held;
    await route.fulfill({ json: priceBody });
  });
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  await started;
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: /loading|running|analy/i })
      .first(),
  ).toBeVisible();
  await page.getByRole("combobox", { name: "Ticker", exact: true }).selectOption("QQQ");
  release();
  await expect(page.getByTestId("analysis-results")).toHaveCount(0);
  await expect(page.getByTestId("backtest-results")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Run analysis", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  await expect(page.getByTestId("analysis-results")).toBeVisible();
  await expect(page.getByTestId("analysis-results").getByText(/QQQ/).first()).toBeVisible();
});

test("empty stored history explains how to choose available data", async ({ page }) => {
  await configureFixture(page);
  await page.route("**/backend/api/v1/prices/SPY?*", async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as Record<string, unknown>;
    await route.fulfill({ json: { ...body, total: 0, has_more: false, bars: [] } });
  });
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  await expect(
    page.getByText(/no (stored )?(price |historical )?(data|bars|observations|history)/i).first(),
  ).toBeVisible();
  await expect(page.getByTestId("analysis-results")).toHaveCount(0);
});

test("unknown ticker API errors retain useful context and allow retry", async ({ page }) => {
  await configureFixture(page);
  await page.route("**/backend/api/v1/prices/SPY?*", (route) =>
    route.fulfill({
      status: 404,
      json: errorBody("unknown_symbol", "Ticker is not supported by the configured provider"),
    }),
  );
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  const alert = page.getByRole("main").getByRole("alert");
  await expect(alert).toContainText("Ticker is not supported");
  await expect(alert).toContainText("e2e-visible-request");
  await expect(page.getByRole("button", { name: "Run analysis", exact: true })).toBeEnabled();
  await expect(page.getByTestId("analysis-results")).toHaveCount(0);
});

test("upstream errors are explicit and do not produce synthetic fallback results", async ({
  page,
}) => {
  await configureFixture(page);
  await page.route("**/backend/api/v1/prices/SPY?*", (route) =>
    route.fulfill({
      status: 503,
      json: errorBody("provider_unavailable", "Configured market data is unavailable; retry later"),
    }),
  );
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Configured market data is unavailable",
  );
  await expect(page.getByTestId("analysis-results")).toHaveCount(0);
  await expect(page.getByTestId("backtest-results")).toHaveCount(0);
});

test("invalid date ranges are rejected before an analysis request", async ({ page }) => {
  await configureFixture(page);
  let analysisRequests = 0;
  page.on("request", (request) => {
    if (/\/backend\/api\/v1\/(prices|cycles|forecasts|backtests)/.test(request.url())) {
      analysisRequests += 1;
    }
  });
  await page.getByLabel("Start date", { exact: true }).fill("2022-11-09");
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    /start.*(before|end)|date range/i,
  );
  expect(analysisRequests).toBe(0);
});

test("catalog failures offer a useful error without enabled analysis controls", async ({
  page,
}) => {
  await page.route("**/backend/api/v1/symbols", (route) =>
    route.fulfill({
      status: 503,
      json: errorBody("database_unavailable", "Symbol catalog is temporarily unavailable"),
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Symbol catalog is temporarily unavailable",
  );
  await expect(page.getByRole("button", { name: "Run analysis", exact: true })).toBeDisabled();
});

test.describe("mobile", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test("fixture controls and results remain readable without page overflow", async ({ page }) => {
    await configureFixture(page, "MU");
    await page.getByRole("button", { name: "Run analysis", exact: true }).click();
    await expect(page.getByTestId("analysis-results")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Forecast", exact: true })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    ).toBeTruthy();
    await page.screenshot({ path: test.info().outputPath("dashboard-mobile.png"), fullPage: true });
    await page.getByRole("combobox", { name: "Ticker", exact: true }).focus();
    await expect(page.getByRole("combobox", { name: "Ticker", exact: true })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Start date", { exact: true })).toBeFocused();
  });
});
