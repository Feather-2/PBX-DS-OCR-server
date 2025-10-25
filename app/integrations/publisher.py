from __future__ import annotations

"""
Publisher abstraction:
- local: return service URLs for downloads
- oss: upload to Aliyun OSS and return signed URLs
"""

import mimetypes
from typing import Dict

from ..config import Settings
from ..storage import JobPaths
from .oss.client import OssClient


class Publisher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._oss: OssClient | None = OssClient(settings) if settings.publish_backend == "oss" else None

    def publish_local(self, task_id: str, paths: JobPaths) -> Dict[str, str]:
        base = f"/v1/tasks/{task_id}"
        return {
            "backend": "local",
            "md_url": f"{base}/result.md",
            "json_url": f"{base}/result.json",
            "zip_url": f"{base}/download.zip",
            "images_url_prefix": f"{base}/result-images",
        }

    def publish_oss(self, task_id: str, paths: JobPaths) -> Dict[str, str]:
        if not self._oss:
            raise RuntimeError("OSS not initialized")
        s = self.settings
        prefix = f"{s.oss_prefix.rstrip('/')}/{task_id}"
        md_key = f"{prefix}/full.md"
        json_key = f"{prefix}/layout.json"
        zip_key = f"{prefix}/result.zip"
        if paths.md_file.exists():
            self._oss.upload_file(md_key, str(paths.md_file), content_type="text/markdown; charset=utf-8")
        if paths.json_file.exists():
            self._oss.upload_file(json_key, str(paths.json_file), content_type="application/json")
        if paths.zip_file.exists():
            self._oss.upload_file(zip_key, str(paths.zip_file), content_type="application/zip")
        if paths.images_dir.exists():
            for p in paths.images_dir.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(paths.output_dir).as_posix()
                    key = f"{prefix}/{rel}"
                    ctype, _ = mimetypes.guess_type(p.name)
                    self._oss.upload_file(key, str(p), content_type=ctype)
        md_url = self._oss.sign_url("GET", md_key, s.oss_sign_expire_seconds) if paths.md_file.exists() else ""
        json_url = self._oss.sign_url("GET", json_key, s.oss_sign_expire_seconds) if paths.json_file.exists() else ""
        zip_url = self._oss.sign_url("GET", zip_key, s.oss_sign_expire_seconds) if paths.zip_file.exists() else ""
        return {
            "backend": "oss",
            "md_url": md_url,
            "json_url": json_url,
            "zip_url": zip_url,
            "images_url_prefix": f"oss://{s.oss_bucket}/{prefix}/images/",
        }

    def publish(self, task_id: str, paths: JobPaths) -> Dict[str, str]:
        return self.publish_oss(task_id, paths) if self.settings.publish_backend == "oss" else self.publish_local(task_id, paths)
