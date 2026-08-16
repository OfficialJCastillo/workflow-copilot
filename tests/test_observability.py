import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.services.observability import metrics_collector
from app.services.observability import RequestMetrics
from main import app


@pytest.fixture(autouse=True)
def reset_request_metrics() -> None:
    metrics_collector.reset()


def test_request_headers_and_structured_log(caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="workflow_copilot.http"):
        response = client.get(
            "/health",
            headers={"X-Request-ID": "release-check-123"},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "release-check-123"
    assert response.headers["Server-Timing"].startswith("app;dur=")

    log_record = next(
        json.loads(record.message)
        for record in caplog.records
        if record.name == "workflow_copilot.http"
    )
    assert log_record == {
        "duration_ms": log_record["duration_ms"],
        "event": "http_request",
        "method": "GET",
        "outcome": "completed",
        "path": "/health",
        "request_id": "release-check-123",
        "status_code": 200,
    }
    assert log_record["duration_ms"] >= 0


def test_invalid_request_id_is_replaced() -> None:
    client = TestClient(app)

    response = client.get("/health", headers={"X-Request-ID": "x" * 129})

    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    assert request_id.isalnum()


def test_metrics_endpoint_reports_request_latency() -> None:
    client = TestClient(app)
    client.get("/health")
    client.get("/health")

    response = client.get("/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "workflow-copilot"
    assert payload["request_count"] == 2
    assert payload["server_error_count"] == 0
    assert payload["latency_ms"]["sample_count"] == 2
    assert payload["latency_ms"]["p50"] >= 0
    assert payload["latency_ms"]["p95"] >= payload["latency_ms"]["p50"]
    assert payload["latency_ms"]["maximum"] >= payload["latency_ms"]["p95"]


def test_percentiles_interpolate_over_recent_samples() -> None:
    metrics = RequestMetrics(max_samples=4)
    for duration_ms in (10.0, 20.0, 30.0, 40.0):
        metrics.record(duration_ms=duration_ms, status_code=200)

    snapshot = metrics.snapshot()

    assert snapshot.request_count == 4
    assert snapshot.latency_ms.p50 == 25.0
    assert snapshot.latency_ms.p95 == 38.5
    assert snapshot.latency_ms.maximum == 40.0
