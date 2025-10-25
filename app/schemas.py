from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    succeeded = "succeeded"
    failed = "failed"
    canceled = "canceled"


class CreateTaskRequest(BaseModel):
    # Upload or URL; FastAPI will use UploadFile via form in route, but we keep schema for docs
    url: Optional[str] = None
    is_ocr: bool = True
    enable_formula: bool = True
    enable_table: bool = True
    language: str = "ch"
    extra_formats: Optional[List[Literal["docx", "html", "latex"]]] = None
    model_version: Optional[str] = None
    bbox: bool = True
    pack_zip: bool = True
    data_id: Optional[str] = None
    page_ranges: Optional[str] = None


class CreateTaskResponse(BaseModel):
    task_id: str
    status: JobStatus


class TaskProgress(BaseModel):
    task_id: str
    status: JobStatus
    queued_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    message: Optional[str] = None
    # Result availability
    result_md: Optional[str] = None
    result_json: Optional[str] = None
    result_zip: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    queue_size: int
    running_workers: int
    max_workers: int
    gpu_free_gb: Optional[float] = None
    gpu_total_gb: Optional[float] = None
    system_memory_free_gb: Optional[float] = None  # 系统内存可用量（GB）
    system_memory_total_gb: Optional[float] = None  # 系统内存总量（GB）
    memory_pressure: bool = False  # 内存压力状态
    queue_capacity: int = 100  # 队列容量
    compute_backend: Optional[str] = None  # gpu/cpu/unknown
    fallback_reason: Optional[str] = None
    mcp_enabled: bool = False  # MCP 功能开关（服务侧元信息）
    model_enabled: bool = True  # 模型是否启用（可用于灰度/轻量部署）
    # Limits
    class Limits(BaseModel):
        max_upload_mb: int
        max_pages: int
        upload_chunk_mb: int
        download_chunk_mb: int

    limits: Limits
