"""Bound analysis JSON bodies, including chunked requests without Content-Length."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_ANALYSIS_BODY_BYTES = 64 * 1024


class AnalysisBodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or not path.startswith(("/api/v1/forecasts/", "/api/v1/backtests", "/api/v1/sectors/"))
        ):
            await self.app(scope, receive, send)
            return
        buffered: list[Message] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > MAX_ANALYSIS_BODY_BYTES or len(buffered) >= 2048:
                request_id = scope.get("state", {}).get("request_id", "unassigned")
                response = JSONResponse(
                    status_code=413,
                    headers={"X-Request-ID": request_id},
                    content={
                        "error": {
                            "code": "payload_too_large",
                            "message": "Analysis body exceeds 64 KiB or fragmentation limit",
                            "request_id": request_id,
                        }
                    },
                )
                await response(scope, receive, send)
                return
            buffered.append(message)
            if not message.get("more_body", False):
                break

        async def replay_receive() -> Message:
            return buffered.pop(0) if buffered else await receive()

        await self.app(scope, replay_receive, send)
