from __future__ import annotations

"""
Aliyun OSS client wrapper: create bucket handle and sign URLs.
"""

from typing import Optional

import oss2  # type: ignore

from ...config import Settings


class OssClient:
    def __init__(self, settings: Settings) -> None:
        if not (
            settings.oss_endpoint
            and settings.oss_bucket
            and settings.oss_access_key_id
            and settings.oss_access_key_secret
        ):
            raise ValueError(
                "Incomplete OSS config: set APP_OSS_ENDPOINT/APP_OSS_BUCKET/APP_OSS_ACCESS_KEY_ID/APP_OSS_ACCESS_KEY_SECRET"
            )
        self.settings = settings
        self.auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
        self.bucket = oss2.Bucket(self.auth, settings.oss_endpoint, settings.oss_bucket)

    def upload_bytes(self, key: str, data: bytes, content_type: Optional[str] = None):
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        self.bucket.put_object(key, data, headers=headers)

    def upload_file(self, key: str, filename: str, content_type: Optional[str] = None):
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        oss2.resumable_upload(self.bucket, key, filename, headers=headers)

    def sign_url(self, method: str, key: str, expire_seconds: int) -> str:
        return self.bucket.sign_url(method, key, expire_seconds)
