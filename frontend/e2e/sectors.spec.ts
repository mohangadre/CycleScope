import { expect, test } from "@playwright/test";

test("actual fixture sectors show matching ratios, quadrants, history and saved replay", async ({
  page,
}) => {
  await page.goto("/sectors");
  await expect(page.getByRole("button", { name: "Compare sectors", exact: true })).toBeEnabled();
  await page.getByLabel("Sector cutoff", { exact: true }).fill("2022-11-08");
  const pending = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/backend/api/v1/sectors/rotation",
  );
  await page.getByRole("button", { name: "Compare sectors", exact: true }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.data_kind).toBe("synthetic");
  expect(body.result.sectors).toHaveLength(8);
  const results = page.getByTestId("sector-results");
  await expect(
    results.getByRole("heading", { name: "Sector rotation", exact: true }),
  ).toBeVisible();
  await expect(
    results.getByRole("heading", { name: "Relative strength history", exact: true }),
  ).toBeVisible();
  await expect(results.locator(".recharts-wrapper > svg.recharts-surface")).toHaveCount(2);
  const table = results.getByRole("table", {
    name: "Sector relative strength observations",
    exact: true,
  });
  await expect(table.getByRole("row")).toHaveCount(9);
  for (const sector of body.result.sectors) {
    const cells = table
      .getByRole("row")
      .filter({ has: page.getByRole("cell").filter({ hasText: sector.ticker }) })
      .getByRole("cell");
    const point = sector.points.at(-1);
    expect(Number(await cells.nth(1).textContent())).toBeCloseTo(point.relative_strength, 5);
    expect(Number(await cells.nth(3).textContent())).toBeCloseTo(point.smoothed_normalized_rs, 3);
    expect((await cells.nth(6).textContent())?.toLowerCase()).toBe(point.quadrant);
  }
  await expect(page.getByText("SYNTHETIC DATA", { exact: true })).toBeVisible();
  await expect(results.getByText("Observed, not forecast", { exact: true })).toBeVisible();
  await results.getByRole("button", { name: "Replay sector snapshot", exact: true }).click();
  await expect(results.getByRole("status")).toContainText("Exact sector replay verified");
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({ path: test.info().outputPath("sector-dashboard.png"), fullPage: true });
});

test("missing sector data remains an explicit error with no substitute results", async ({
  page,
}) => {
  await page.goto("/sectors");
  await expect(page.getByRole("button", { name: "Compare sectors", exact: true })).toBeEnabled();
  await page.route("**/backend/api/v1/sectors/rotation?*", (route) =>
    route.fulfill({
      status: 422,
      json: {
        error: {
          code: "insufficient_data",
          message: "XLK lacks matching sector history; load the configured feed",
          request_id: "sector-missing",
        },
      },
    }),
  );
  await page.getByRole("button", { name: "Compare sectors", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "XLK lacks matching sector history",
  );
  await expect(page.getByTestId("sector-results")).toHaveCount(0);
});

test("changing a sector window cancels and clears the prior comparison", async ({ page }) => {
  await page.goto("/sectors");
  await page.getByRole("button", { name: "Compare sectors", exact: true }).click();
  await expect(page.getByTestId("sector-results")).toBeVisible();
  await page.getByLabel("Momentum window (trading sessions)", { exact: true }).fill("10");
  await expect(page.getByTestId("sector-results")).toHaveCount(0);
  await page.getByRole("button", { name: "Compare sectors", exact: true }).click();
  await expect(
    page.getByTestId("sector-results").getByText("10-session momentum", { exact: true }),
  ).toBeVisible();
});

test("mobile sector page contains charts and a scrollable table without page overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/sectors");
  await page.getByRole("button", { name: "Compare sectors", exact: true }).click();
  await expect(page.getByTestId("sector-results").getByRole("table")).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBeTruthy();
  await page.screenshot({ path: test.info().outputPath("sector-mobile.png"), fullPage: true });
});
