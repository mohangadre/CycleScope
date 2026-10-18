import { expect, test } from "@playwright/test";

test("shorter dates keep actual price history and offer an explicit smaller lookback", async ({
  page,
}) => {
  let calculations = 0;
  page.on("request", (request) => {
    if (/\/api\/v1\/(cycles|forecasts)\//.test(request.url())) calculations++;
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Run analysis", exact: true })).toBeEnabled();
  await page.getByLabel("Start date", { exact: true }).fill("2021-01-04");
  await page.getByLabel("End date", { exact: true }).fill("2021-12-31");
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  const hint = page.getByTestId("short-history");
  await expect(hint).toContainText("252 trading sessions");
  await expect(page.getByRole("heading", { name: "Price history", exact: true })).toBeVisible();
  expect(calculations).toBe(0);
  await hint.getByRole("button", { name: "Set lookback to 252 sessions", exact: true }).click();
  await expect(page.getByLabel("Lookback (trading sessions)", { exact: true })).toHaveValue("252");
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Forecast", exact: true })).toBeVisible();
  expect(calculations).toBe(2);
  await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
  await page.getByLabel("Initial training (trading sessions)", { exact: true }).fill("200");
  await page.getByRole("button", { name: "Run backtest", exact: true }).click();
  await expect(page.getByTestId("backtest-results")).toContainText("2 folds");
  await expect(page.getByTestId("backtest-results")).toContainText("40 scored targets");

  await page.getByLabel("End date", { exact: true }).fill("2021-01-08");
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  await expect(page.getByTestId("short-history")).toContainText("at least 32 trading sessions");
  await expect(page.getByRole("heading", { name: "Price history", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Forecast", exact: true })).toHaveCount(0);
  expect(calculations).toBe(2);
});

test("stored coverage changes with the selected ticker without source substitution", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByTestId("price-coverage")).toContainText("Stored SPY: 2020-01-02");
  await page.getByRole("combobox", { name: "Ticker", exact: true }).selectOption("QQQ");
  await expect(page.getByTestId("price-coverage")).toContainText("Stored QQQ: 2020-01-02");
  await expect(page.getByTestId("price-coverage")).not.toContainText("Stored SPY:");
  await expect(
    page.getByRole("button", { name: "Download selected dates from Alpaca", exact: true }),
  ).toHaveCount(0);
});

test("explicit date download sends the chosen range and preserves feed failures", async ({
  page,
}) => {
  // Only source/coverage metadata and the failure are intercepted; no prices are invented.
  await page.route("**/backend/api/v1/symbols", async (route) => {
    const original = await route.fetch();
    await route.fulfill({
      json: { ...(await original.json()), provider: "alpaca-iex", data_kind: "real" },
    });
  });
  await page.route("**/backend/api/v1/prices/SPY/coverage", (route) =>
    route.fulfill({
      json: {
        ticker: "SPY",
        provider: "alpaca-iex",
        data_kind: "real",
        adjustment_basis: "split_dividend_adjusted",
        first_session: null,
        last_session: null,
        session_count: 0,
        last_ingested_at: null,
        latest_completed_session: "2024-03-28",
      },
    }),
  );
  let submitted: unknown;
  await page.route("**/backend/api/v1/prices/SPY/refresh", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({
      status: 503,
      json: {
        error: {
          code: "provider_unavailable",
          message: "Alpaca returned HTTP 403; check feed access/limits",
          request_id: "download-failed",
        },
      },
    });
  });
  await page.goto("/");
  await expect(page.getByTestId("price-coverage")).toContainText("No stored SPY prices");
  await page.getByLabel("Start date", { exact: true }).fill("2024-01-02");
  await page.getByLabel("End date", { exact: true }).fill("2024-03-28");
  await page
    .getByRole("button", { name: "Download selected dates from Alpaca", exact: true })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Alpaca returned HTTP 403");
  expect(submitted).toEqual({ start: "2024-01-02", end: "2024-03-28" });
  await expect(page.getByTestId("analysis-results")).toHaveCount(0);
});
