import { expect, test } from "@playwright/test";

test("real source controls use the runtime ingestion cutoff; no prices are mocked", async ({
  page,
}) => {
  // Only catalog metadata is changed. No market/forecast values are supplied.
  await page.route("**/backend/api/v1/symbols", async (route) => {
    const original = await route.fetch();
    const catalog = await original.json();
    await route.fulfill({
      json: { ...catalog, provider: "alpaca-iex", data_kind: "real" },
    });
  });
  await page.goto("/");
  await expect(page.getByLabel("End date", { exact: true })).toHaveValue("2024-03-28");
  await expect(page.getByLabel("Start date", { exact: true })).toHaveValue("2022-04-04");
  await expect(page.getByText("REAL HISTORICAL DATA", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Sector rotation", exact: true }).click();
  await expect(page.getByLabel("Sector cutoff", { exact: true })).toHaveValue("2024-03-28");
});
