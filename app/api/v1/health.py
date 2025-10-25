from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Request

from ...schemas import HealthResponse
from ...utils.gpu import get_gpu_memory_gb, get_system_memory_gb, check_memory_pressure


router = APIRouter(tags=["health"]) 


@router.get("/healthz", response_model=HealthResponse)
async def healthz(request: Request):
    app = request.app
    settings = app.state.settings
    job_queue = app.state.job_queue
    start_ts = app.state.started_at
    uptime = (datetime.now().timestamp() - start_ts)

    # GPU 显存
    gpu_mem = get_gpu_memory_gb(settings.gpu_index)
    free_gb = total_gb = None
    if gpu_mem:
        free_gb, total_gb = gpu_mem

    # 系统内存
    sys_mem = get_system_memory_gb()
    sys_free_gb = sys_total_gb = None
    if sys_mem:
        sys_free_gb, sys_total_gb = sys_mem

    # 检查内存压力
    min_sys_mem = getattr(settings, "min_system_memory_gb", 2.0)
    memory_pressure = check_memory_pressure(min_sys_mem)

    mm = app.state.model_manager
    compute = getattr(mm, "runtime_device", None)
    if not compute or compute == "unknown":
        compute = "gpu" if gpu_mem else "cpu"

    limits = HealthResponse.Limits(
        max_upload_mb=settings.max_upload_mb,
        max_pages=settings.max_pages,
        upload_chunk_mb=settings.upload_chunk_mb,
        download_chunk_mb=settings.download_chunk_mb,
    )

    return HealthResponse(
        status="ok",
        uptime_seconds=uptime,
        queue_size=job_queue.queue_size(),
        running_workers=job_queue.running_workers(),
        max_workers=settings.max_workers,
        gpu_free_gb=free_gb,
        gpu_total_gb=total_gb,
        system_memory_free_gb=sys_free_gb,
        system_memory_total_gb=sys_total_gb,
        memory_pressure=memory_pressure,
        queue_capacity=job_queue.queue_capacity(),
        compute_backend=compute,
        fallback_reason=getattr(mm, "fallback_reason", None),
        mcp_enabled=bool(getattr(settings, "enable_mcp", False)),
        model_enabled=bool(getattr(settings, "enable_model", True)),
        limits=limits,
    )
