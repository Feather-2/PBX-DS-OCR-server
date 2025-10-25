from __future__ import annotations

"""
FastAPI 入口：
- 初始化配置与服务（模型管理器、流水线、队列）
- 注册路由与中间件
"""

import time
from fastapi import FastAPI
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

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins or ["*"],
        allow_credentials=True,
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

    return app


app = create_app()




