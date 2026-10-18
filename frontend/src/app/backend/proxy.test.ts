import { afterEach, expect, it, vi } from "vitest";
import { GET, POST } from "./[...path]/route";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
const context = (path: string) => ({ params: Promise.resolve({ path: path.split("/") }) });

it("accepts the actual browser Host when Next normalizes the internal URL", async () => {
  const upstream = vi
    .fn<typeof fetch>()
    .mockResolvedValue(
      Response.json({ kind: "forecast" }, { headers: { "X-Request-ID": "upstream-request" } }),
    );
  vi.stubGlobal("fetch", upstream);
  vi.stubEnv("CYCLESCOPE_API_URL", "http://127.0.0.1:8011");
  const request = new Request("http://localhost:3001/backend/api/v1/forecasts/SPY", {
    method: "POST",
    headers: { Origin: "http://127.0.0.1:3001", Host: "127.0.0.1:3001" },
    body: "{}",
  });
  const response = await POST(request, context("api/v1/forecasts/SPY"));
  expect(response.status).toBe(200);
  expect(response.headers.get("X-Request-ID")).toBe("upstream-request");
  expect(String(upstream.mock.calls[0][0])).toBe("http://127.0.0.1:8011/api/v1/forecasts/SPY");
});

it("rejects an arbitrary path without making an upstream request", async () => {
  const upstream = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", upstream);
  expect((await GET(new Request("http://localhost/backend/admin"), context("admin"))).status).toBe(
    404,
  );
  expect(upstream).not.toHaveBeenCalled();
});

it("rejects oversized bodies before forwarding them", async () => {
  const upstream = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", upstream);
  const request = new Request("http://localhost/backend/api/v1/backtests", {
    method: "POST",
    body: "x".repeat(65537),
  });
  expect((await POST(request, context("api/v1/backtests"))).status).toBe(413);
  expect(upstream).not.toHaveBeenCalled();
});

it("returns a useful backend-unavailable error without exposing the destination", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>().mockRejectedValue(new Error("private address and transport internals")),
  );
  const response = await GET(
    new Request("http://localhost/backend/api/v1/symbols"),
    context("api/v1/symbols"),
  );
  expect(response.status).toBe(503);
  expect(await response.text()).not.toContain("private address");
});
