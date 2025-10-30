from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse

from ...security.auth import verify_api_key
from ...integrations.publisher import Publisher
from ...storage import get_job_paths
from ...utils.security import validate_task_id, validate_path_in_storage


router = APIRouter(prefix="/v1", tags=["publish"], dependencies=[Depends(verify_api_key)])


def _ctx(request: Request):
    app = request.app
    return app.state.settings, app.state.publisher, app.state.token_manager


@router.post("/tasks/{task_id}/publish")
async def publish_task(
    request: Request,
    task_id: str,
    backend: Optional[Literal["local", "oss"]] = Query(None),
):
    if not validate_task_id(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    settings, publisher, _ = _ctx(request)
    # Temporary backend override for this call
    pub = Publisher(settings) if backend and backend != settings.publish_backend else publisher

    job_root = validate_path_in_storage(settings.storage_root, Path(settings.storage_root) / task_id)
    if not job_root.exists():
        raise HTTPException(status_code=404, detail="Task not found")
    paths = get_job_paths(settings.storage_root, task_id)
    info = pub.publish(task_id, paths)
    return {"code": 0, "data": info}


@router.post("/tasks/{task_id}/tokens")
async def create_download_token(
    request: Request,
    task_id: str,
    kind: Literal["md", "json", "zip"],
    max_downloads: int = 1,
    expire_seconds: int = 3600,
):
    if not validate_task_id(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    settings, _, token_mgr = _ctx(request)
    job_root = validate_path_in_storage(settings.storage_root, Path(settings.storage_root) / task_id)
    if not job_root.exists():
        raise HTTPException(status_code=404, detail="Task not found")

    if settings.publish_backend == "oss":
        prefix = f"{settings.oss_prefix.rstrip('/')}/{task_id}"
        mapping = {
            "md": f"{prefix}/full.md",
            "json": f"{prefix}/layout.json",
            "zip": f"{prefix}/result.zip",
        }
        t = token_mgr.create_token(
            task_id,
            kind=kind,
            object_key=mapping[kind],
            max_downloads=max(1, max_downloads),
            expire_seconds=max(1, expire_seconds),
        )
    else:
        mapping = {
            "md": job_root / "output" / "full.md",
            "json": job_root / "output" / "layout.json",
            "zip": job_root / "result.zip",
        }
        fp = mapping[kind]
        if not fp.exists():
            raise HTTPException(status_code=404, detail="Result not generated yet")
        t = token_mgr.create_token(
            task_id,
            kind=kind,
            file_path=str(fp),
            max_downloads=max(1, max_downloads),
            expire_seconds=max(1, expire_seconds),
        )
    return {
        "code": 0,
        "data": {
            "token": t.token,
            "download_url": f"/v1/download/{t.token}",
            "remain": t.remain,
            "expire_at": t.expire_at,
        },
    }


@router.get("/download/{token}")
async def download_by_token(request: Request, token: str):
    settings, _, token_mgr = _ctx(request)
    t = token_mgr.consume(token)
    if not t:
        raise HTTPException(status_code=404, detail="invalid or expired token")
    if t.backend == "oss":
        url = token_mgr.sign_for_token(t)
        if not url:
            raise HTTPException(status_code=500, detail="signing failed")
        return RedirectResponse(url)
    else:
        if not t.file_path:
            raise HTTPException(status_code=404, detail="File path not found")
        # 验证文件路径在 storage_root 内
        file_path = validate_path_in_storage(settings.storage_root, t.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        filename = file_path.name
        return FileResponse(file_path, filename=filename)

