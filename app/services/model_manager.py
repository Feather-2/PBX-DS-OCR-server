from __future__ import annotations

"""
模型管理器：
- 惰性加载 DeepSeek-OCR（Transformers）
- 基于显存的并发门控
- 空闲卸载（释放显存）
- GPU→CPU 回退，并在健康检查中报告状态
"""

import threading
import time
from contextlib import contextmanager
from typing import Any, Optional
import os
import logging

from ..config import Settings, load_settings
from ..utils.gpu import get_gpu_memory_gb, get_system_memory_gb, check_memory_pressure
from .dsocr_model import DeepSeekOCRModel
from .dsocr_vllm import DeepSeekOCRVLLM


class ModelManager:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or load_settings()
        self._lock = threading.RLock()
        self._inference_lock = threading.Lock()  # 推理全局锁，确保模型单例使用
        self._model: Optional[Any] = None
        self._busy_gpu_tasks = 0
        self._last_used_ts = time.time()
        self._stop_event = threading.Event()
        self._idle_thread = threading.Thread(
            target=self._idle_watcher, name="model-idle-watcher", daemon=True
        )
        self._idle_thread.start()
        self.runtime_device: str = "unknown"  # gpu/cpu/unknown
        self.fallback_reason: Optional[str] = None
        self._logger = logging.getLogger("dsocr-service")
        self.backend: str = (self.settings.backend or "hf").lower()
        # 若强制 CPU，尽早隐藏 GPU（在导入/构造模型之前生效）
        if getattr(self.settings, "force_cpu", False):
            os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
            os.environ.setdefault("NVIDIA_VISIBLE_DEVICES", "")

    def _try_set_device(self) -> str:
        """根据配置与环境选择设备并设置，返回实际设备 'gpu' 或 'cpu'。"""
        try:
            import torch

            if getattr(self.settings, "force_cpu", False):
                try:
                    self._logger.info("runtime device selected: cpu (forced)")
                except Exception:
                    pass
                return "cpu"
            if torch.cuda.is_available():
                try:
                    # 记录 GPU 设备选择，内存门控在推理上下文中实现
                    self._logger.info("runtime device selected: gpu")
                    return "gpu"
                except Exception as e:
                    self.fallback_reason = f"set_device gpu failed: {e}"
                    try:
                        self._logger.warning("fallback to cpu: %s", self.fallback_reason)
                    except Exception:
                        pass
                    return "cpu"
            else:
                try:
                    self._logger.info("runtime device selected: cpu (no cuda)")
                except Exception:
                    pass
                return "cpu"
        except Exception:
            try:
                self._logger.warning("torch import failed, fallback to cpu")
            except Exception:
                pass
            return "cpu"

    def _load_impl(self):
        # DeepSeek-OCR lazy loader (hf or vllm)
        device = self._try_set_device()
        try:
            backend = (self.settings.backend or "hf").lower()
            if backend == "vllm":
                try:
                    model = DeepSeekOCRVLLM(self.settings)
                    self.backend = "vllm"
                except Exception as e:
                    # Graceful fallback to HF backend if vLLM is unavailable or model config invalid
                    self.fallback_reason = f"vLLM init failed: {e}"
                    try:
                        self._logger.warning("vLLM init failed, falling back to HF: %s", e)
                    except Exception:
                        pass
                    model = DeepSeekOCRModel(self.settings)
                    self.backend = "hf"
            else:
                model = DeepSeekOCRModel(self.settings)
                self.backend = "hf"
            self.runtime_device = device
            try:
                self._logger.info("DeepSeek-OCR loaded (backend=%s, device=%s)", self.backend, self.runtime_device)
            except Exception:
                pass
            return model
        except Exception as e:
            # load failure
            self.runtime_device = "unknown"
            self.fallback_reason = f"load failed: {e}"
            raise

    def get_model(self):
        with self._lock:
            if self._model is None:
                self._model = self._load_impl()
            self._last_used_ts = time.time()
            return self._model

    def unload(self):
        with self._lock:
            if self._model is not None:
                # 显式释放（尽力释放显存缓存）
                self._model = None
            self._empty_cuda_cache()

    def _empty_cuda_cache(self):
        try:
            import torch

            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
        except Exception:
            pass

    def stop(self):
        self._stop_event.set()
        # 等待 idle watcher 退出
        if self._idle_thread.is_alive():
            self._idle_thread.join(timeout=1.0)

    def _idle_watcher(self):
        # 周期检查是否空闲足够长时间，若是则卸载模型
        while not self._stop_event.is_set():
            time.sleep(1.0)
            try:
                with self._lock:
                    idle_sec = time.time() - self._last_used_ts
                    if (
                        self._model is not None
                        and self._busy_gpu_tasks == 0
                        and idle_sec >= self.settings.idle_unload_seconds
                    ):
                        self._model = None
                        self._empty_cuda_cache()
            except Exception:
                # 不影响主流程
                pass

    def _allowed_gpu_concurrency(self) -> int:
        # 根据显存动态计算允许并发数
        if not self.settings.dynamic_workers:
            return max(1, min(self.settings.max_workers, 1))

        # CPU 模式限流为 1
        if getattr(self, "runtime_device", "cpu") != "gpu":
            return 1

        mem = get_gpu_memory_gb(self.settings.gpu_index)
        if not mem:
            # 无 GPU 视为串行
            return 1

        free_gb, total_gb = mem
        # 预留一点显存，避免 OOM
        reserve = max(0.0, self.settings.reserve_gpu_mem_gb)
        usable = max(0.0, free_gb - reserve)
        per = max(0.1, self.settings.mem_per_job_gb)
        allowed = int(usable // per)
        if allowed <= 0:
            allowed = 1  # 至少放行 1 个

        # 记录显存状态用于调试
        try:
            self._logger.debug(
                f"GPU memory check: free={free_gb:.2f}GB, total={total_gb:.2f}GB, "
                f"usable={usable:.2f}GB, per_job={per:.2f}GB, allowed={allowed}"
            )
        except Exception:
            pass

        return max(1, min(self.settings.max_workers, allowed))

    def _check_memory_available(self) -> bool:
        """检查当前显存/内存是否足够运行新任务"""
        # 1. 检查系统内存压力
        min_sys_mem = getattr(self.settings, "min_system_memory_gb", 2.0)
        if check_memory_pressure(min_sys_mem):
            try:
                sys_mem = get_system_memory_gb()
                if sys_mem:
                    avail, total = sys_mem
                    self._logger.warning(
                        f"System memory pressure: {avail:.2f}GB available of {total:.2f}GB total"
                    )
            except Exception:
                pass
            return False  # 系统内存压力大，拒绝新任务

        # 2. GPU 模式下检查显存
        if getattr(self, "runtime_device", "cpu") != "gpu":
            return True  # CPU 模式只需检查系统内存

        mem = get_gpu_memory_gb(self.settings.gpu_index)
        if not mem:
            return False

        free_gb, _ = mem
        required = self.settings.reserve_gpu_mem_gb + self.settings.mem_per_job_gb
        return free_gb > required

    @contextmanager
    def inference_context(self, wait_interval: float = 0.5, timeout: Optional[float] = None):
        """
        推理上下文：全局串行化推理，防止多模型实例同时加载导致 OOM。
        结合 GPU 显存门控，确保内存安全。
        """
        start_ts = time.time()
        inference_acquired = False
        gpu_slot_acquired = False

        try:
            # 1. vLLM 后端不需要全局串行锁
            if self.backend != "vllm":
                while not self._inference_lock.acquire(blocking=False):
                    if timeout is not None and (time.time() - start_ts) > timeout:
                        raise TimeoutError("等待推理锁超时")
                    time.sleep(wait_interval)
                inference_acquired = True

            # 2. 获取模型实例
            model = self.get_model()

            # 3. GPU 模式下获取显存配额（vLLM 交由内部管理，这里跳过）
            if getattr(self, "runtime_device", "cpu") == "gpu" and self.backend != "vllm":
                while True:
                    with self._lock:
                        # 实时检查显存是否足够
                        if not self._check_memory_available():
                            # 显存不足，等待其他任务释放
                            pass
                        else:
                            allowed = self._allowed_gpu_concurrency()
                            if self._busy_gpu_tasks < allowed:
                                self._busy_gpu_tasks += 1
                                gpu_slot_acquired = True
                                break
                    if timeout is not None and (time.time() - start_ts) > timeout:
                        raise TimeoutError("等待 GPU 配额超时")
                    time.sleep(wait_interval)

            yield model

        finally:
            # 释放 GPU 配额
            if gpu_slot_acquired:
                with self._lock:
                    self._busy_gpu_tasks = max(0, self._busy_gpu_tasks - 1)
                    self._last_used_ts = time.time()

            # 释放推理锁
            if inference_acquired:
                self._inference_lock.release()

    @contextmanager
    def gpu_slot(self, wait_interval: float = 0.5, timeout: Optional[float] = None):
        """
        GPU 门控：在推理前进入该上下文，确保并发不超过显存允许范围。
        CPU 模式直接放行。

        注意：推荐使用 inference_context() 替代此方法，它提供更强的 OOM 保护。
        """
        if getattr(self, "runtime_device", "cpu") != "gpu":
            # CPU 模式，无需门控
            yield
            return
        start_ts = time.time()
        acquired = False
        try:
            while True:
                with self._lock:
                    allowed = self._allowed_gpu_concurrency()
                    if self._busy_gpu_tasks < allowed:
                        self._busy_gpu_tasks += 1
                        acquired = True
                        break
                if timeout is not None and (time.time() - start_ts) > timeout:
                    raise TimeoutError("等待 GPU 配额超时")
                time.sleep(wait_interval)
            yield
        finally:
            with self._lock:
                if acquired:
                    self._busy_gpu_tasks = max(0, self._busy_gpu_tasks - 1)
                self._last_used_ts = time.time()
