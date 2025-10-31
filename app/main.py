from __future__ import annotations

"""
FastAPI 入口：
- 初始化配置与服务（模型管理器、流水线、队列）
- 注册路由与中间件
"""

import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .security.auth import verify_api_key
from .config import Settings, load_settings
from .services.model_manager import ModelManager
from .services.pipeline import DocumentPipeline
from .services.queue import JobQueue
from .domain.job import Job
from .api.v1.tasks import router as tasks_router
from .api.v1.health import router as health_router
from .api.v1.publish import router as publish_router
from .api.v1.infer import router as infer_router
from .integrations.publisher import Publisher
from .security.tokens import TokenManager
from .logging import setup_logging
from .monitoring import metrics as app_metrics
from .security.console import sign_session, verify_session
from .security.rate_limit import RateLimiter
from .middleware import (
    request_logger,
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)


def create_app() -> FastAPI:
    settings: Settings = load_settings()
    app = FastAPI(title="DeepSeek-OCR 文档解析服务 (v1)")
    setup_logging(settings.log_level)

    # CORS (configurable)
    try:
        raw_origins = getattr(settings, "cors_allow_origins", "*")
        allow_origins = ["*"]
        if isinstance(raw_origins, str):
            s = raw_origins.strip()
            if s:
                allow_origins = [x.strip() for x in s.split(",") if x.strip()]
        elif isinstance(raw_origins, (list, tuple)):
            allow_origins = [str(x).strip() for x in raw_origins if str(x).strip()]

        allow_credentials = bool(getattr(settings, "cors_allow_credentials", True))
        # If wildcard origins are used with credentials, relax credentials to comply with CORS spec
        if any(o == "*" for o in allow_origins) and allow_credentials:
            allow_credentials = False
            try:
                import logging as _logging
                _logging.getLogger("dsocr-service").warning(
                    "CORS: '*' with credentials is not allowed; disabling credentials."
                )
            except Exception:
                pass
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allow_origins,
            allow_origin_regex=getattr(settings, "cors_allow_origin_regex", None),
            allow_credentials=allow_credentials,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    except Exception:
        # Fallback to permissive CORS if configuration fails
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # 依赖项注册（状态）
    app.state.settings = settings
    app.state.started_at = time.time()
    app.state.model_manager = ModelManager(settings)
    app.state.pipeline = DocumentPipeline(app.state.model_manager, settings)
    app.state.job_queue = JobQueue(app.state.pipeline, settings)
    # 暴露 Job 类型给路由内部按需引用（type: ignore 使用）
    app.state.job_queue.Job = Job  # type: ignore[attr-defined]
    app.state.publisher = Publisher(settings)
    app.state.token_manager = TokenManager(settings)
    # Session secret for console auth (ephemeral if not provided)
    import os
    app.state.session_secret = settings.session_secret or os.urandom(32).hex()

    # Metrics should be registered before static mount to avoid being shadowed
    if settings.metrics_enabled:
        app_metrics.register(app)

    @app.on_event("startup")
    async def on_startup():
        app.state.job_queue.start()

    @app.on_event("shutdown")
    async def on_shutdown():
        app.state.job_queue.stop()
        app.state.model_manager.stop()
        # Gracefully stop background cleanup threads for rate limiters
        try:
            rl_default.stop()
        except Exception:
            pass
        try:
            rl_login.stop()
        except Exception:
            pass

    # Rate limiters
    rl_default = RateLimiter(
        rate_per_sec=max(0.1, float(settings.rate_limit_rps)),
        burst=max(1, int(settings.rate_limit_burst)),
    )
    rl_login = RateLimiter(
        rate_per_sec=max(0.1, float(settings.login_rate_per_min) / 60.0),
        burst=max(1, int(settings.login_rate_burst)),
    )

    # 控制台登录/登出
    @app.get("/login")
    async def login_page():
        if not settings.console_enabled:
            return {"code": 404, "msg": "console disabled"}
        return (
            """<!doctype html><meta charset=\"utf-8\"><title>Login</title>
<style>body{font-family:system-ui;margin:48px;max-width:420px}input{padding:8px;font-size:14px;width:100%}button{padding:8px 12px;margin-top:8px}</style>
<h2>Console Login</h2>
<form method=\"POST\" action=\"/login\">
  <input type=\"password\" name=\"password\" placeholder=\"Password\" />
  <button type=\"submit\">Login</button>
  <p style=\"color:#666;font-size:12px\">需要设置 APP_CONSOLE_PASSWORD</p>
  <p><a href=\"/\">返回主页</a></p>
</form>"""
        )

    @app.post("/login")
    async def do_login(request: Request):
        from fastapi.responses import HTMLResponse, RedirectResponse

        if not settings.console_enabled:
            return HTMLResponse("console disabled", status_code=404)
        form = await request.form()
        pwd = (form.get("password") or "").strip()
        if not settings.console_password:
            return HTMLResponse("console password not set", status_code=403)
        if pwd != settings.console_password:
            return HTMLResponse("invalid password", status_code=401)
        # issue session cookie
        exp = int(time.time()) + max(60, settings.console_session_max_age)
        token = sign_session(app.state.session_secret, "console", exp)
        resp = RedirectResponse(url="/", status_code=302)
        resp.set_cookie(
            "dsocr_console", token, max_age=settings.console_session_max_age,
            httponly=True, secure=settings.cookie_secure, samesite="lax", path="/"
        )
        return resp

    @app.get("/logout")
    async def do_logout():
        from fastapi.responses import RedirectResponse

        resp = RedirectResponse(url="/", status_code=302)
        resp.delete_cookie("dsocr_console", path="/")
        return resp

    # 路由
    app.include_router(health_router)
    app.include_router(tasks_router)
    app.include_router(publish_router)
    app.include_router(infer_router)

    # 静态前端（简单控制台）
    try:
        app.mount("/", StaticFiles(directory="web", html=True), name="web")
    except Exception:
        pass

    # 日志与异常处理
    app.middleware("http")(request_logger)
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # 全局限流（轻量，按 IP）
    @app.middleware("http")
    async def rate_limiter(request: Request, call_next):
        if not settings.rate_limit_enabled:
            return await call_next(request)
        path = request.url.path or "/"
        if path in (settings.rate_limit_exempt_paths or []):
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        allowed = True
        if path == "/login" and request.method.upper() == "POST":
            allowed = rl_login.allow(client)
        else:
            allowed = rl_default.allow(client)
        if not allowed:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=429,
                content={"code": 429, "msg": "Too Many Requests"},
            )
        return await call_next(request)

    # 控制台访问保护（仅对 web 控制台资源生效）
    @app.middleware("http")
    async def console_protect(request: Request, call_next):
        path = request.url.path or "/"
        # 跳过 API 与登录、健康/指标
        if path.startswith("/v1/") or path in ("/healthz", "/metrics", "/login") or path.startswith("/layout-parsing"):
            return await call_next(request)
        if not settings.console_enabled:
            return await call_next(request)
        if not settings.console_password:
            return await call_next(request)
        token = request.cookies.get("dsocr_console")
        if token and verify_session(app.state.session_secret, token):
            return await call_next(request)
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            """<!doctype html><meta charset=\"utf-8\"><title>Login Required</title>
<style>body{font-family:system-ui;margin:48px;max-width:480px}input{padding:8px;font-size:14px;width:100%}button{padding:8px 12px;margin-top:8px}</style>
<h2>Login Required</h2>
<p>Web 控制台已启用访问保护。请输入密码登录。</p>
<form method=\"POST\" action=\"/login\"> <input type=\"password\" name=\"password\" placeholder=\"Password\" /> <button type=\"submit\">Login</button> </form>
<p style=\"color:#666;font-size:12px\">环境变量：APP_CONSOLE_PASSWORD</p>""",
            status_code=401,
        )

    return app


app = create_app()




