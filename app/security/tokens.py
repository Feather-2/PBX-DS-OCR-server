from __future__ import annotations

"""
下载令牌管理：
- 生成带次数/有效期限制的 token
- 校验并消费 token
- 后端可为 local 或 oss；oss 在消费时生成一次性签名 URL 并 302 跳转
"""

import json
import secrets
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional

from ..config import Settings
from ..integrations.oss.client import OssClient


@dataclass
class Token:
    token: str
    backend: str  # local/oss
    task_id: str
    kind: str  # md/json/zip
    object_key: Optional[str] = None  # oss 对象 key（当 backend=oss）
    file_path: Optional[str] = None  # 本地文件路径（当 backend=local）
    max_downloads: int = 1
    remain: int = 1
    expire_at: float = 0.0

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d


class TokenManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._path = Path(settings.token_store_path)
        self._lock = threading.RLock()
        self._data: Dict[str, Dict] = {}
        self._oss: Optional[OssClient] = None
        if settings.publish_backend == "oss":
            self._oss = OssClient(settings)
        self._load()

    def _load(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}

    def _save(self):
        tmp = json.dumps(self._data, ensure_ascii=False, indent=2)
        self._path.write_text(tmp, encoding="utf-8")

    def create_token(
        self,
        task_id: str,
        *,
        kind: str,
        file_path: Optional[str] = None,
        object_key: Optional[str] = None,
        max_downloads: int = 1,
        expire_seconds: int = 3600,
    ) -> Token:
        tok = secrets.token_urlsafe(24)
        t = Token(
            token=tok,
            backend=self.settings.publish_backend,
            task_id=task_id,
            kind=kind,
            object_key=object_key,
            file_path=file_path,
            max_downloads=max_downloads,
            remain=max_downloads,
            expire_at=time.time() + max(1, expire_seconds),
        )
        with self._lock:
            self._data[tok] = t.to_dict()
            self._save()
        return t

    def consume(self, token: str) -> Optional[Token]:
        with self._lock:
            raw = self._data.get(token)
            if not raw:
                return None
            t = Token(**raw)
            if time.time() > t.expire_at:
                self._data.pop(token, None)
                self._save()
                return None
            if t.remain <= 0:
                self._data.pop(token, None)
                self._save()
                return None
            # 扣减并保存
            t.remain -= 1
            self._data[token] = t.to_dict()
            self._save()
            return t

    def sign_for_token(self, t: Token) -> Optional[str]:
        if t.backend == "oss":
            if not (self._oss and t.object_key):
                return None
            # 每次消费时动态签名，保证即时有效
            return self._oss.sign_url("GET", t.object_key, self.settings.oss_sign_expire_seconds)
        else:
            return None
