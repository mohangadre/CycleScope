from fastapi.testclient import TestClient

from cyclescope.api.app import create_app
from cyclescope.api.limits import MAX_ANALYSIS_BODY_BYTES


def test_large_body_rejected_before_model_validation_without_database() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/forecasts/SPY",
            content=b"x" * (MAX_ANALYSIS_BODY_BYTES + 1),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"
        assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_chunked_body_cannot_bypass_limit() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/backtests",
            content=iter([b"x" * 32768] * 3),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413
