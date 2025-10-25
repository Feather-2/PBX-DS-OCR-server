from __future__ import annotations

"""
Lightweight Prometheus metrics for the server.

Exposes /metrics and provides helpers to update counters and gauges
without heavy background threads. GPU memory gauges are refreshed on
each scrape to keep overhead minimal.
"""

from typing import Callable
from fastapi import FastAPI, Request, Response
from starlette.responses import PlainTextResponse

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from ..utils.gpu import get_gpu_memory_gb


# HTTP request metrics
REQUEST_COUNTER = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request duration seconds", ["method", "path"]
)

# Task metrics
TASKS_SUBMITTED = Counter("tasks_submitted_total", "Total submitted tasks")
TASKS_SUCCEEDED = Counter("tasks_succeeded_total", "Total succeeded tasks")
TASKS_FAILED = Counter("tasks_failed_total", "Total failed tasks")

# Queue metrics
QUEUE_SIZE = Gauge("queue_size", "Current job queue size")
RUNNING_WORKERS = Gauge("running_workers", "Running worker threads")

# GPU metrics (updated on scrape)
GPU_MEMORY_FREE_GB = Gauge("gpu_memory_free_gb", "GPU free memory (GB)")
GPU_MEMORY_TOTAL_GB = Gauge("gpu_memory_total_gb", "GPU total memory (GB)")


def register(app: FastAPI):
    """Register middleware and /metrics route."""

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next: Callable):
        import time

        start = time.time()
        path = request.url.path
        method = request.method
        # Skip /metrics self-instrumentation latency to avoid recursion/noise
        if path == "/metrics":
            return await call_next(request)

        response: Response = await call_next(request)

        try:
            REQUEST_COUNTER.labels(method=method, path=path, status=str(response.status_code)).inc()
            REQUEST_LATENCY.labels(method=method, path=path).observe(max(0.0, time.time() - start))
        except Exception:
            pass
        return response

    @app.get("/metrics")
    async def metrics_endpoint():
        # refresh GPU metrics on scrape
        try:
            mem = get_gpu_memory_gb(0)
            if mem:
                free_gb, total_gb = mem
                GPU_MEMORY_FREE_GB.set(free_gb)
                GPU_MEMORY_TOTAL_GB.set(total_gb)
        except Exception:
            pass
        payload = generate_latest()
        return PlainTextResponse(content=payload.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


def update_queue(size: int, workers: int):
    try:
        QUEUE_SIZE.set(size)
        RUNNING_WORKERS.set(workers)
    except Exception:
        pass


def task_submitted():
    try:
        TASKS_SUBMITTED.inc()
    except Exception:
        pass


def task_succeeded():
    try:
        TASKS_SUCCEEDED.inc()
    except Exception:
        pass


def task_failed():
    try:
        TASKS_FAILED.inc()
    except Exception:
        pass

