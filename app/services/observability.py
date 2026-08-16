from collections import deque
import json
import logging
import math
import os
import re
from threading import Lock
from time import monotonic
from time import perf_counter
from datetime import UTC
from datetime import datetime
import uuid

from app.schemas.models import LatencyMetrics
from app.schemas.models import ServiceMetricsResponse
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


REQUEST_ID_HEADER = "X-Request-ID"
SERVER_TIMING_HEADER = "Server-Timing"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

request_logger = logging.getLogger("workflow_copilot.http")
request_logger.setLevel(os.getenv("WORKFLOW_LOG_LEVEL", "INFO").upper())


class RequestMetrics:
    def __init__(self, max_samples: int = 1_000) -> None:
        self._max_samples = max_samples
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._started_at = datetime.now(UTC)
            self._started_monotonic = monotonic()
            self._request_count = 0
            self._server_error_count = 0
            self._latencies_ms: deque[float] = deque(maxlen=self._max_samples)

    def record(self, *, duration_ms: float, status_code: int) -> None:
        with self._lock:
            self._request_count += 1
            if status_code >= 500:
                self._server_error_count += 1
            self._latencies_ms.append(duration_ms)

    def snapshot(self) -> ServiceMetricsResponse:
        with self._lock:
            request_count = self._request_count
            server_error_count = self._server_error_count
            latencies_ms = sorted(self._latencies_ms)
            started_at = self._started_at
            uptime_seconds = monotonic() - self._started_monotonic

        return ServiceMetricsResponse(
            service="workflow-copilot",
            started_at=started_at.isoformat(),
            uptime_seconds=round(uptime_seconds, 3),
            request_count=request_count,
            server_error_count=server_error_count,
            server_error_rate=round(server_error_count / request_count, 4) if request_count else 0.0,
            latency_ms=LatencyMetrics(
                sample_count=len(latencies_ms),
                p50=self._percentile(latencies_ms, 0.50),
                p95=self._percentile(latencies_ms, 0.95),
                maximum=round(latencies_ms[-1], 3) if latencies_ms else 0.0,
            ),
        )

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        if len(values) == 1:
            return round(values[0], 3)

        rank = (len(values) - 1) * percentile
        lower_index = math.floor(rank)
        upper_index = math.ceil(rank)
        lower = values[lower_index]
        upper = values[upper_index]
        interpolated = lower + (upper - lower) * (rank - lower_index)
        return round(interpolated, 3)


metrics_collector = RequestMetrics()


def _request_id(request: Request) -> str:
    candidate = request.headers.get(REQUEST_ID_HEADER)
    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _request_id(request)
        request.state.request_id = request_id
        started = perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - started) * 1_000
            metrics_collector.record(duration_ms=duration_ms, status_code=500)
            self._log_request(
                request=request,
                request_id=request_id,
                status_code=500,
                duration_ms=duration_ms,
                outcome="unhandled_exception",
            )
            raise

        duration_ms = (perf_counter() - started) * 1_000
        metrics_collector.record(duration_ms=duration_ms, status_code=response.status_code)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[SERVER_TIMING_HEADER] = f"app;dur={duration_ms:.3f}"
        self._log_request(
            request=request,
            request_id=request_id,
            status_code=response.status_code,
            duration_ms=duration_ms,
            outcome="completed",
        )
        return response

    @staticmethod
    def _log_request(
        *,
        request: Request,
        request_id: str,
        status_code: int,
        duration_ms: float,
        outcome: str,
    ) -> None:
        request_logger.info(
            json.dumps(
                {
                    "duration_ms": round(duration_ms, 3),
                    "event": "http_request",
                    "method": request.method,
                    "outcome": outcome,
                    "path": request.url.path,
                    "request_id": request_id,
                    "status_code": status_code,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
