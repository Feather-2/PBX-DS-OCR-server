from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


async def request_logger(request: Request, call_next: Callable):
    start = time.time()
    logger = logging.getLogger("dsocr-service")
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        dur = (time.time() - start) * 1000
        # 根据响应状态码选择日志级别
        status_code = 0
        if response is not None:
            status_code = getattr(response, 'status_code', 0)
        else:
            # 如果响应为空，可能是异常情况
            status_code = 500

        if status_code >= 500:
            log_level = logging.ERROR
        elif status_code >= 400:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO

        # 不记录 Authorization 头
        logger.log(
            log_level,
            f"{request.method} {request.url.path} -> {status_code} {dur:.1f}ms"
        )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": exc.detail},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"code": 422, "msg": str(exc)})


async def unhandled_exception_handler(request: Request, exc: Exception):
    logging.getLogger("dsocr-service").exception("Unhandled error")
    return JSONResponse(status_code=500, content={"code": 500, "msg": "internal error"})
