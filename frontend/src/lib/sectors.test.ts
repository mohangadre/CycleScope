import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { ApiClient, type SectorResponse } from "./api";

const fixture = JSON.parse(readFileSync("../docs/experiments/synthetic-mvp-week4.json", "utf8"))
  .sectors as SectorResponse;
const query = {
  asOf: "2022-11-08",
  lookbackSessions: 126,
  momentumSessions: 20,
  smoothingSessions: 5,
};
const response = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });

describe("sector transport contracts using the recorded synthetic experiment", () => {
  it("preserves all observed values and uses bounded same-origin query parameters", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response(fixture));
    expect(await new ApiClient(fetcher).getSectorRotation(query)).toEqual(fixture);
    expect(String(fetcher.mock.calls[0][0])).toBe(
      "/backend/api/v1/sectors/rotation?as_of=2022-11-08&lookback_sessions=126&momentum_sessions=20&smoothing_sessions=5",
    );
  });

  it("rejects duplicate sectors and missing observations", async () => {
    const duplicate = structuredClone(fixture);
    duplicate.result.sectors[1].ticker = duplicate.result.sectors[0].ticker;
    const missing = structuredClone(fixture);
    missing.result.sectors[0].points.pop();
    for (const body of [duplicate, missing]) {
      const client = new ApiClient(vi.fn<typeof fetch>().mockResolvedValue(response(body)));
      await expect(client.getSectorRotation(query)).rejects.toThrow("coverage is incomplete");
    }
  });

  it("rejects a mismatched session or reference instead of joining by array position", async () => {
    const shifted = structuredClone(fixture);
    shifted.result.sectors[1].points[1].session_date = "2022-05-13";
    const reference = structuredClone(fixture);
    reference.result.sectors[0].points[0].normalized_rs = 101;
    for (const body of [shifted, reference]) {
      const client = new ApiClient(vi.fn<typeof fetch>().mockResolvedValue(response(body)));
      await expect(client.getSectorRotation(query)).rejects.toThrow("do not match");
    }
  });

  it("rejects future observations and a nonfinite ratio", async () => {
    const future = structuredClone(fixture);
    future.result.sectors[0].points.at(-1)!.session_date = "2022-11-09";
    const nonfinite = structuredClone(fixture);
    nonfinite.result.sectors[0].points[1].relative_strength = Infinity;
    for (const body of [future, nonfinite]) {
      const client = new ApiClient(vi.fn<typeof fetch>().mockResolvedValue(response(body)));
      await expect(client.getSectorRotation(query)).rejects.toThrow("Invalid relative strength");
    }
  });

  it("replays the immutable sector report via POST and forwards cancellation", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response(fixture));
    const controller = new AbortController();
    expect(await new ApiClient(fetcher).replaySector(fixture.run_id, controller.signal)).toEqual(
      fixture,
    );
    expect(fetcher.mock.calls[0][0]).toBe(`/backend/api/v1/sectors/runs/${fixture.run_id}/replay`);
    expect(fetcher.mock.calls[0][1]).toMatchObject({ method: "POST", signal: controller.signal });
  });
});
