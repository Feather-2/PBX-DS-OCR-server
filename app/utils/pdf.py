from __future__ import annotations

"""
PDF 工具函数：安全获取页数。
解析失败返回 None（不抛异常），便于上层做兜底逻辑。
"""

from pathlib import Path
from typing import Optional


def get_pdf_page_count(path: Path) -> Optional[int]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return None

    try:
        with path.open("rb") as f:
            reader = PdfReader(f, strict=False)
            return int(len(reader.pages))
    except Exception:
        return None

