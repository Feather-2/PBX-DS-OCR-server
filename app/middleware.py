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
    try:
        response = await call_next(request)
        return response
    finally:
        dur = (time.time() - start) * 1000
        # 不记录 Authorization 头
        logging.getLogger("dsocr-service").info(
            f"{request.method} {request.url.path} -> {getattr(request.state, 'status', '')} {dur:.1f}ms"
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
