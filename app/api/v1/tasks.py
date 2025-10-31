from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse

from ...security.auth import verify_api_key
from ...schemas import CreateTaskRequest, CreateTaskResponse, JobStatus, TaskProgress
from ...storage import init_storage, new_job, load_status
from ...utils.pdf import get_pdf_page_count
from ...utils.security import validate_task_id, validate_path_in_storage
from ...domain.job import Job


router = APIRouter(prefix="/v1", tags=["tasks"], dependencies=[Depends(verify_api_key)])


def _services(request: Request):
    # Resolve services from app.state
    app = request.app
    return app.state.settings, app.state.job_queue


@router.post("/tasks", response_model=CreateTaskResponse)
async def create_task_json(
    request: Request,
    payload: CreateTaskRequest = Body(...),
):
    settings, job_queue = _services(request)

    if not settings.enable_model:
        raise HTTPException(status_code=503, detail="Model disabled by APP_ENABLE_DS_MODEL=false")

    if not payload.url:
        raise HTTPException(status_code=400, detail="Missing url. Or use /v1/tasks/upload to upload a file.")

    storage_root = init_storage(settings.storage_root)

    # Remote file size pre-check (HEAD Content-Length)
    try:
        import requests

        resp = requests.head(payload.url, timeout=10, allow_redirects=True)
        size_hdr = resp.headers.get("Content-Length") if resp is not None else None
        if size_hdr and size_hdr.isdigit():
            size_bytes = int(size_hdr)
            max_size = max(1, settings.max_upload_mb) * 1024 * 1024
            if size_bytes > max_size:
                raise HTTPException(status_code=413, detail=f"Remote file too large (> {settings.max_upload_mb}MB)")
    except Exception:
        # If HEAD fails, we'll enforce limits after download
        pass

    task_id, paths = new_job(storage_root.as_posix(), filename="remote.pdf")

    job_options = payload.model_dump()
    job_options["is_url"] = True

    # 检查队列是否已满
    if job_queue.is_queue_full():
        raise HTTPException(status_code=503, detail="Server busy: task queue is full. Please retry later.")

    # 提交任务
    job = Job(task_id=task_id, paths=paths, options=job_options)
    if not job_queue.submit(job):
        raise HTTPException(status_code=503, detail="Server busy: failed to enqueue task. Please retry later.")

    return CreateTaskResponse(task_id=task_id, status=JobStatus.queued)


@router.post("/tasks/upload", response_model=CreateTaskResponse)
async def create_task_upload(
    request: Request,
    file: UploadFile = File(...),
    is_ocr: bool = True,
    enable_formula: bool = True,
    enable_table: bool = True,
    language: str = "ch",
    bbox: bool = True,
    pack_zip: bool = True,
    page_ranges: Optional[str] = None,
    model_version: Optional[str] = None,
):
    settings, job_queue = _services(request)
    if not settings.enable_model:
        raise HTTPException(status_code=503, detail="Model disabled by APP_ENABLE_DS_MODEL=false")
    storage_root = init_storage(settings.storage_root)
    task_id, paths = new_job(storage_root.as_posix(), filename=file.filename or "input.pdf")

    # Stream upload to file with size limit (使用原子写入)
    chunk_size = max(1, settings.upload_chunk_mb) * 1024 * 1024
    max_size = max(1, settings.max_upload_mb) * 1024 * 1024
    total = 0
    tmp_file = paths.input_file.with_suffix(paths.input_file.suffix + ".tmp")
    try:
        with tmp_file.open("wb") as out:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size:
                    raise HTTPException(status_code=413, detail=f"File too large (> {settings.max_upload_mb}MB)")
                out.write(chunk)
        # 原子替换：仅在写入成功后才替换原文件
        tmp_file.replace(paths.input_file)
    except Exception:
        # 清理临时文件
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except Exception:
                pass
        raise
    finally:
        await file.close()

    # PDF page limit (if PDF)
    if paths.input_file.suffix.lower() == ".pdf":
        pages = get_pdf_page_count(paths.input_file)
        if pages is not None and pages > settings.max_pages:
            raise HTTPException(status_code=400, detail=f"PDF pages exceed limit {settings.max_pages}")

    job_options = dict(
        is_url=False,
        is_ocr=is_ocr,
        enable_formula=enable_formula,
        enable_table=enable_table,
        language=language,
        bbox=bbox,
        pack_zip=pack_zip,
        page_ranges=page_ranges,
        model_version=model_version,
    )

    # 检查队列是否已满
    if job_queue.is_queue_full():
        raise HTTPException(status_code=503, detail="Server busy: task queue is full. Please retry later.")

    # 提交任务
    job = Job(task_id=task_id, paths=paths, options=job_options)
    if not job_queue.submit(job):
        raise HTTPException(status_code=503, detail="Server busy: failed to enqueue task. Please retry later.")

    return CreateTaskResponse(task_id=task_id, status=JobStatus.queued)


@router.get("/tasks/{task_id}", response_model=TaskProgress)
async def get_task(request: Request, task_id: str):
    if not validate_task_id(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    settings, job_queue = _services(request)
    job = job_queue.get(task_id)
    if not job:
        data = load_status(settings.storage_root, task_id)
        if not data:
            raise HTTPException(status_code=404, detail="Task not found")
        return TaskProgress(
            task_id=task_id,
            status=JobStatus(data.get("status", "queued")),
            queued_at=datetime.fromtimestamp(data.get("queued_at", 0)),
            started_at=(
                datetime.fromtimestamp(data["started_at"]) if data.get("started_at") else None
            ),
            finished_at=(
                datetime.fromtimestamp(data["finished_at"]) if data.get("finished_at") else None
            ),
            message=data.get("message"),
            result_md=f"/v1/tasks/{task_id}/result.md",
            result_json=f"/v1/tasks/{task_id}/result.json",
            result_zip=f"/v1/tasks/{task_id}/download.zip",
        )

    return TaskProgress(
        task_id=task_id,
        status=job.status,
        queued_at=datetime.fromtimestamp(job.queued_at),
        started_at=(datetime.fromtimestamp(job.started_at) if job.started_at else None),
        finished_at=(datetime.fromtimestamp(job.finished_at) if job.finished_at else None),
        message=job.message,
        result_md=f"/v1/tasks/{task_id}/result.md",
        result_json=f"/v1/tasks/{task_id}/result.json",
        result_zip=f"/v1/tasks/{task_id}/download.zip",
    )


@router.get("/tasks/{task_id}/result.md")
async def download_md(request: Request, task_id: str):
    if not validate_task_id(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    settings, _ = _services(request)
    md = validate_path_in_storage(settings.storage_root, Path(settings.storage_root) / task_id / "output" / "full.md")
    if not md.exists():
        raise HTTPException(status_code=404, detail="Result not generated yet")
    return FileResponse(md)


@router.get("/tasks/{task_id}/result.json")
async def download_json(request: Request, task_id: str):
    if not validate_task_id(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    settings, _ = _services(request)
    jf = validate_path_in_storage(settings.storage_root, Path(settings.storage_root) / task_id / "output" / "layout.json")
    if not jf.exists():
        raise HTTPException(status_code=404, detail="Result not generated yet")
    return FileResponse(jf)


@router.get("/tasks/{task_id}/download.zip")
async def download_zip(request: Request, task_id: str):
    if not validate_task_id(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    settings, _ = _services(request)
    zf = validate_path_in_storage(settings.storage_root, Path(settings.storage_root) / task_id / "result.zip")
    if not zf.exists():
        raise HTTPException(status_code=404, detail="Archive not generated yet")
    return FileResponse(zf, filename=f"{task_id}.zip")


@router.delete("/tasks/{task_id}")
async def delete_task(request: Request, task_id: str):
    import shutil

    if not validate_task_id(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    settings, _ = _services(request)
    root = validate_path_in_storage(settings.storage_root, Path(settings.storage_root) / task_id)

    if not root.exists():
        raise HTTPException(status_code=404, detail="Task not found")
    shutil.rmtree(root, ignore_errors=True)
    return {"code": 0, "msg": "deleted"}


@router.get("/tasks/{task_id}/result-images/{path:path}")
async def get_image(request: Request, task_id: str, path: str):
    """Serve local images safely (prevent path traversal)."""
    from urllib.parse import unquote

    if not validate_task_id(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    settings, _ = _services(request)
    base = Path(settings.storage_root) / task_id / "output" / "images"
    base_resolved = base.resolve()

    # 只取路径的最后一部分（文件名），防止路径遍历
    try:
        # 解析并清理路径
        path_parts = Path(unquote(path)).parts
        # 只使用文件名部分，忽略任何目录遍历尝试
        filename = path_parts[-1] if path_parts else ""

        # 验证文件名安全（只允许字母、数字、点、下划线、连字符），并限制扩展名
        if not filename or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in filename):
            raise HTTPException(status_code=403, detail="Invalid filename")
        # 文件名长度限制
        maxlen = max(32, int(getattr(settings, "result_images_filename_maxlen", 128)))
        if len(filename) > maxlen:
            raise HTTPException(status_code=403, detail="Filename too long")
        # 扩展名白名单（可配置）
        allowed_cfg = getattr(settings, "result_images_allowed_exts", ".png,.jpg,.jpeg,.webp,.bmp")
        allowed_ext = {x.strip().lower() for x in str(allowed_cfg).split(",") if x.strip()}
        from pathlib import Path as _P
        if _P(filename).suffix.lower() not in allowed_ext:
            raise HTTPException(status_code=403, detail="Invalid file type")

        # 是否允许子目录（默认不允许，仅文件名）
        allow_sub = bool(getattr(settings, "result_images_allow_subdirs", False))
        if allow_sub:
            # 如果允许子目录，则对传入路径进行规范化并校验
            norm_rel = Path(unquote(path)).as_posix().lstrip("/\\")
            target = (base_resolved / norm_rel).resolve()
        else:
            target = (base_resolved / filename).resolve()

        # 确保目标文件是 base 的子路径（使用 relative_to 更安全）
        target.relative_to(base_resolved)

        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(target)
    except (ValueError, OSError) as exc:
        # ValueError: 路径不在 base 内
        # OSError: 文件系统错误
        raise HTTPException(status_code=403, detail="Invalid path") from exc
