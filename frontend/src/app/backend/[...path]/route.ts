/** A runtime-configured, fixed-destination proxy. No provider credentials reach the browser. */
export const dynamic = "force-dynamic";
const SYMBOL = "[A-Z][A-Z0-9.-]{0,14}";
const UUID = "[a-fA-F0-9-]{36}";
const READ = new RegExp(
  `^(health|api/v1/(symbols|prices/${SYMBOL}|cycles/${SYMBOL}|analyses/${UUID}|backtests/${UUID}|sectors/rotation|sectors/runs/${UUID}))$`,
);
const WRITE = new RegExp(
  `^api/v1/(forecasts/${SYMBOL}|backtests(?:/${UUID}/replay)?|sectors/runs/${UUID}/replay)$`,
);
const MAX_BODY = 64 * 1024;

function failure(message: string, status: number) {
  return Response.json(
    { error: { code: "dashboard_proxy_error", message, request_id: "dashboard-proxy" } },
    { status },
  );
}

async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const path = (await context.params).path.join("/");
  if (!(request.method === "GET" ? READ : WRITE).test(path))
    return failure("Unknown API route.", 404);
  if (request.method === "POST" && request.headers.has("origin")) {
    try {
      // Next can normalize request.url to localhost. Host retains the actual
      // origin used by the browser, including the listening port.
      if (new URL(request.headers.get("origin")!).host !== request.headers.get("host"))
        return failure("Cross-origin requests are not accepted.", 403);
    } catch {
      return failure("Invalid request origin.", 403);
    }
  }
  let destination: URL;
  try {
    destination = new URL(process.env.CYCLESCOPE_API_URL ?? "http://127.0.0.1:8000");
  } catch {
    return failure("The backend address is not configured correctly.", 503);
  }
  if (
    !["http:", "https:"].includes(destination.protocol) ||
    destination.username ||
    destination.password ||
    destination.pathname !== "/" ||
    destination.search ||
    destination.hash
  )
    return failure("The backend address is not configured correctly.", 503);
  destination.pathname = `/${path}`;
  destination.search = new URL(request.url).search;
  const chunks: Uint8Array[] = [];
  if (request.body) {
    const reader = request.body.getReader();
    let bytes = 0;
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      bytes += next.value.byteLength;
      if (bytes > MAX_BODY) {
        await reader.cancel();
        return failure("Analysis body exceeds 64 KiB.", 413);
      }
      chunks.push(next.value);
    }
  }
  const body = new Blob(chunks as BlobPart[]);
  try {
    const upstream = await fetch(destination, {
      method: request.method,
      body: request.method === "POST" ? body : undefined,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(60_000)]),
    });
    const headers = new Headers({
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      "Cache-Control": "no-store",
    });
    const requestId = upstream.headers.get("x-request-id");
    if (requestId) headers.set("X-Request-ID", requestId);
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch {
    return failure(
      "Cannot reach the configured backend. Check that the API is running and retry.",
      503,
    );
  }
}

export const GET = proxy;
export const POST = proxy;
