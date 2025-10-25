from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import load_settings


security = HTTPBearer(auto_error=False)


def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    settings = load_settings()
    if not settings.api_keys:
        # 当要求强制认证但未配置密钥时，拒绝请求
        if getattr(settings, "require_auth", True):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required")
        # 否则视为开发模式放行
        return None
    if credentials is None or not credentials.scheme or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")
    token = (credentials.credentials or '').strip()
    if settings.require_key_prefix and not token.startswith(settings.require_key_prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token prefix")
    if token not in settings.api_keys:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return token
