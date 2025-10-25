from __future__ import annotations

"""
GPU 工具：封装 NVML 查询，提供显存信息。
在无 GPU 或 NVML 不可用时，自动降级为 None。
同时提供系统内存监控。
"""

from typing import Optional, Tuple


def get_gpu_memory_gb(gpu_index: int = 0) -> Optional[Tuple[float, float]]:
    try:
        from pynvml import (
            nvmlInit,
            nvmlShutdown,
            nvmlDeviceGetHandleByIndex,
            nvmlDeviceGetMemoryInfo,
        )
    except Exception:
        return None

    try:
        nvmlInit()
        handle = nvmlDeviceGetHandleByIndex(gpu_index)
        info = nvmlDeviceGetMemoryInfo(handle)
        free_gb = info.free / (1024 ** 3)
        total_gb = info.total / (1024 ** 3)
        return float(free_gb), float(total_gb)
    except Exception:
        return None
    finally:
        try:
            nvmlShutdown()
        except Exception:
            pass


def get_system_memory_gb() -> Optional[Tuple[float, float]]:
    """
    获取系统内存信息（可用内存，总内存），单位 GB。
    返回 (available_gb, total_gb) 或 None（获取失败时）。
    """
    try:
        import psutil
        mem = psutil.virtual_memory()
        available_gb = mem.available / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)
        return float(available_gb), float(total_gb)
    except Exception:
        return None


def check_memory_pressure(min_available_gb: float = 2.0) -> bool:
    """
    检查系统内存是否处于压力状态。
    返回 True 表示内存压力大（可用内存不足），False 表示正常。
    """
    mem = get_system_memory_gb()
    if not mem:
        return False  # 无法获取，默认认为正常
    available_gb, _ = mem
    return available_gb < min_available_gb
