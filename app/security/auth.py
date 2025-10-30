from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import load_settings


security = HTTPBearer(auto_error=False)

# 缓存 settings 和 api_keys set，避免每次请求都重新加载
_settings_cache = None
_api_keys_set_cache = None


def _get_settings(request: Request = None):
    """从 request.app.state 获取 settings，如果没有则加载并缓存"""
    global _settings_cache, _api_keys_set_cache

    if request and hasattr(request.app, 'state') and hasattr(request.app.state, 'settings'):
        settings = request.app.state.settings
    else:
        # Fallback: 如果没有 request，使用缓存或重新加载
        if _settings_cache is None:
            _settings_cache = load_settings()
        settings = _settings_cache

    # 更新 api_keys set 缓存（如果 settings 发生变化）
    if _api_keys_set_cache is None or settings.api_keys != getattr(_settings_cache, 'api_keys', None):
        _api_keys_set_cache = set(settings.api_keys) if settings.api_keys else set()
        _settings_cache = settings

    return settings, _api_keys_set_cache


def verify_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    验证 API Key。
    优先从 request.app.state 获取 settings 以提高性能。
    """
    # 从 request.app.state 获取 settings（已在应用启动时设置）
    try:
        settings = request.app.state.settings
        # 使用 set 进行快速查找
        if not hasattr(request.app.state, '_api_keys_set'):
            request.app.state._api_keys_set = set(settings.api_keys) if settings.api_keys else set()
        api_keys_set = request.app.state._api_keys_set
    except AttributeError:
        # Fallback: 如果没有 app.state，使用全局缓存
        settings, api_keys_set = _get_settings(request)

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
    # 使用 set 进行 O(1) 查找
    if token not in api_keys_set:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return token
