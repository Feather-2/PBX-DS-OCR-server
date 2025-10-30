from __future__ import annotations

"""
安全工具函数：验证输入参数防止路径遍历等安全问题
"""

import uuid
from pathlib import Path
from fastapi import HTTPException


def validate_task_id(task_id: str) -> bool:
    """
    验证 task_id 是否为有效的 UUID 格式。
    防止路径遍历攻击。
    """
    try:
        uuid.UUID(task_id)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def validate_path_in_storage(storage_root: str | Path, target_path: str | Path) -> Path:
    """
    验证目标路径是否在存储根目录内，防止路径遍历攻击。

    Args:
        storage_root: 存储根目录
        target_path: 目标路径

    Returns:
        Path: 解析后的目标路径

    Raises:
        HTTPException: 如果路径不在存储根目录内
    """
    storage_root = Path(storage_root).resolve()
    target = Path(target_path).resolve()

    try:
        # 确保目标路径是 storage_root 的子路径
        target.relative_to(storage_root)
        return target
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid path: path traversal detected") from exc

