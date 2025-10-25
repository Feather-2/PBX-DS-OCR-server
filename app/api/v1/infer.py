from __future__ import annotations

import base64
import io
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ...security.auth import verify_api_key


router = APIRouter(tags=["inference"], dependencies=[Depends(verify_api_key)])


def _img_to_b64(image) -> str:
    try:
        from PIL import Image  # type: ignore

        buf = io.BytesIO()
        # 统一导出 JPEG，便于前端快速渲染
        image.convert("RGB").save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


@router.post("/layout-parsing")
async def layout_parsing(request: Request, payload: Dict[str, Any]):
    """
    DeepSeek-OCR 同步文档解析接口。
    请求体为 JSON，核心字段：
    - input: str (本地路径或 URL)
    - 其它可选参数按模型 predict 签名动态注入

    返回体采用 {logId, errorCode, errorMsg, result} 形式，result 内部为：
    - layoutParsingResults: List[...]
    - dataInfo: Dict
    """
    app = request.app
    mm = app.state.model_manager

    input_arg = str(payload.get("input", "")).strip()
    if not input_arg:
        raise HTTPException(status_code=400, detail="missing 'input'")

    # 解析控制参数（尽量与服务参数一致）
    # predict 常用参数
    is_ocr = bool(payload.get("is_ocr", True))
    enable_formula = bool(payload.get("enable_formula", True))
    enable_table = bool(payload.get("enable_table", True))
    language = str(payload.get("language", "ch"))
    page_ranges = payload.get("page_ranges")
    model_version = payload.get("model_version")
    return_images = bool(payload.get("return_images", False))

    # 可能存在的可选参数（预留占位以适配未来扩展）
    optional_args = {}

    # 动态调用 predict，避免因不同版本引发未知参数错误
    items: List[Dict[str, Any]] = []
    log_id = uuid.uuid4().hex
    try:
        timeout = max(60, app.state.settings.load_timeout_seconds)
        with mm.inference_context(timeout=timeout) as model:
            # 根据签名构造 kwargs
            import inspect

            sig = inspect.signature(model.predict)
            kwargs = dict(
                is_ocr=is_ocr,
                enable_formula=enable_formula,
                enable_table=enable_table,
                language=language,
                page_ranges=page_ranges,
            )
            mv = model_version
            if mv and "model_version" in sig.parameters:
                kwargs["model_version"] = mv
            # 注入可选参数：仅当 predict 签名包含该参数时传入
            for k, v in optional_args.items():
                if v is not None and k in sig.parameters:
                    kwargs[k] = v

            outputs = model.predict(input_arg, **kwargs)

        # 组装返回结果（对齐文档字段语义；字段名尽量一致）
        for res in outputs:
            # prunedResult：使用 res.json（若包含 res 字段则剥离 input_path/page_index）
            pruned = {}
            try:
                j = getattr(res, "json", None)
                if callable(j):
                    j = j()
                if isinstance(j, dict):
                    if "res" in j and isinstance(j["res"], dict):
                        pruned = dict(j["res"])  # 剥离外层
                    else:
                        pruned = dict(j)
                    for key in ("input_path", "page_index"):
                        if key in pruned:
                            pruned.pop(key, None)
            except Exception:
                pruned = {}

            # markdown
            markdown_obj: Dict[str, Any] = {"text": "", "images": {}, "isStart": False, "isEnd": False}
            try:
                md = getattr(res, "markdown", None)
                if callable(md):
                    md = md()
                if isinstance(md, dict):
                    text = md.get("markdown_texts") or md.get("markdown_text") or ""
                    if isinstance(text, str):
                        markdown_obj["text"] = text
                    if return_images:
                        imgs = md.get("markdown_images", {}) or {}
                        if isinstance(imgs, dict):
                            for rel, image in imgs.items():
                                b64 = _img_to_b64(image)
                                if b64:
                                    markdown_obj["images"][str(rel)] = b64
            except Exception:
                pass

            # 可视化输出图（layout/order 等）
            output_images = None
            if return_images:
                try:
                    img_dict = getattr(res, "img", None)
                    if callable(img_dict):
                        img_dict = img_dict()
                    if isinstance(img_dict, dict):
                        tmp = {}
                        for k, v in img_dict.items():
                            b64 = _img_to_b64(v)
                            if b64:
                                tmp[str(k)] = b64
                        output_images = tmp or None
                except Exception:
                    output_images = None

            items.append(
                {
                    "prunedResult": pruned,
                    "markdown": markdown_obj,
                    "outputImages": output_images,
                    "inputImage": None,  # 当前不返回输入图像
                }
            )

        return {
            "logId": log_id,
            "errorCode": 0,
            "errorMsg": "Success",
            "result": {
                "layoutParsingResults": items,
                "dataInfo": {"input": input_arg},
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        return {
            "logId": log_id,
            "errorCode": 500,
            "errorMsg": str(e),
        }
