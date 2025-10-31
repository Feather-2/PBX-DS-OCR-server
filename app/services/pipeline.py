from __future__ import annotations

"""
文档解析流水线：
负责将输入（本地文件路径或 URL）交给 DeepSeek-OCR 适配器，
保存 Markdown / JSON 与图片，并打包 zip（可选）。
加入文件大小与 PDF 页数限制校验。
"""

from pathlib import Path
from typing import Optional
import time
import logging

import requests

from ..config import Settings, load_settings
from ..storage import JobPaths, pack_zip
from .model_manager import ModelManager


class DocumentPipeline:
    def __init__(self, model_manager: ModelManager, settings: Optional[Settings] = None) -> None:
        self.settings = settings or load_settings()
        self.mm = model_manager
        self._logger = logging.getLogger("dsocr-service")

    def _ensure_download(self, url: str, dst: Path):
        dst.parent.mkdir(parents=True, exist_ok=True)
        chunk = max(1, self.settings.download_chunk_mb) * 1024 * 1024
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with dst.open("wb") as f:
                for part in r.iter_content(chunk_size=chunk):
                    if not part:
                        continue
                    f.write(part)

    def run(
        self,
        input_path_or_url: str,
        job_paths: JobPaths,
        *,
        is_url: bool = False,
        bbox: bool = True,
        pack: bool = True,
        is_ocr: bool = True,
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        page_ranges: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> None:
        # 如果是 URL，先下载到 input_file
        if is_url:
            self._ensure_download(input_path_or_url, job_paths.input_file)
            input_arg = job_paths.input_file.as_posix()
        else:
            input_arg = input_path_or_url

        # 文件大小限制（在下载或本地就绪后执行）
        try:
            size_bytes = job_paths.input_file.stat().st_size
            max_size = max(1, self.settings.max_upload_mb) * 1024 * 1024
            if size_bytes > max_size:
                raise ValueError(f"文件大小超过限制 {self.settings.max_upload_mb}MB")
        except Exception:
            pass

        # PDF 页数限制（若是 PDF）
        pages_count = None
        if job_paths.input_file.suffix.lower() == ".pdf":
            try:
                from ..utils.pdf import get_pdf_page_count

                pages_count = get_pdf_page_count(job_paths.input_file)
            except Exception:
                pages_count = None
            if pages_count is not None and pages_count > self.settings.max_pages:
                raise ValueError(f"PDF 页数超过限制 {self.settings.max_pages}")

        # 记录基础信息并计时
        try:
            self._logger.info(
                "pipeline start: pages=%s, is_url=%s, model_version=%s, opts(formula=%s, table=%s, bbox=%s, lang=%s)",
                pages_count,
                is_url,
                model_version,
                enable_formula,
                enable_table,
                bbox,
                language,
            )
        except Exception:
            pass
        t0 = time.time()

        # 自动分批处理大 PDF
        if (
            self.settings.enable_auto_batch
            and pages_count is not None
            and pages_count > self.settings.batch_page_size
            and page_ranges is None  # 用户未指定范围时才自动分批
        ):
            self._run_batched(
                input_arg,
                job_paths,
                pages_count,
                is_ocr=is_ocr,
                enable_formula=enable_formula,
                enable_table=enable_table,
                language=language,
                model_version=model_version,
            )
        else:
            # 单次处理
            self._run_single(
                input_arg,
                job_paths,
                is_ocr=is_ocr,
                enable_formula=enable_formula,
                enable_table=enable_table,
                language=language,
                page_ranges=page_ranges,
                model_version=model_version,
            )

        # 可选打包
        if pack:
            pack_zip(job_paths)

    def _run_single(
        self,
        input_arg: str,
        job_paths: JobPaths,
        *,
        is_ocr: bool = True,
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        page_ranges: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> None:
        """单次执行推理"""
        # 使用推理上下文（全局串行 + GPU 门控）
        timeout = max(60, self.settings.load_timeout_seconds)
        with self.mm.inference_context(timeout=timeout) as model:
            # Build kwargs safely based on predict signature
                try:
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
                    outputs = model.predict(input_arg, **kwargs)
                except Exception:
                    # Fallback without model_version if anything unexpected
                    outputs = model.predict(
                        input_arg,
                        is_ocr=is_ocr,
                        enable_formula=enable_formula,
                        enable_table=enable_table,
                        language=language,
                        page_ranges=page_ranges,
                    )

        # 保存结果（模型本身提供保存方法）
        job_paths.output_dir.mkdir(parents=True, exist_ok=True)
        for res in outputs:
            try:
                res.save_to_json(save_path=job_paths.output_dir.as_posix())
            except Exception:
                pass
            try:
                res.save_to_markdown(save_path=job_paths.output_dir.as_posix())
            except Exception:
                pass

        # 额外生成合并后的 full.md，并保存 markdown_images 到 images/
        try:
            md_parts = []
            images_items = []
            for res in outputs:
                try:
                    info = res.markdown
                    if isinstance(info, dict):
                        t = info.get("markdown_texts") or info.get("markdown_text")
                        if isinstance(t, str) and t.strip():
                            md_parts.append(t)
                        mi = info.get("markdown_images", {})
                        if isinstance(mi, dict) and mi:
                            images_items.append(mi)
                except Exception:
                    continue
            if md_parts:
                job_paths.md_file.parent.mkdir(parents=True, exist_ok=True)
                job_paths.md_file.write_text("\n\n".join(md_parts), encoding="utf-8")
            for item in images_items:
                for rel_path, image in item.items():
                    try:
                        # 归一化相对路径，限制在 images 子目录内，防止越界写入
                        rel = str(rel_path).lstrip("/\\")
                        # 只保留文件名，避免目录穿越
                        from pathlib import Path as _P
                        fname = _P(rel).name
                        out_path = (job_paths.images_dir / fname)
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        image.save(out_path)
                    except Exception:
                        continue
        except Exception:
            pass

    def _run_batched(
        self,
        input_arg: str,
        job_paths: JobPaths,
        total_pages: int,
        *,
        is_ocr: bool = True,
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        model_version: Optional[str] = None,
    ) -> None:
        """分批执行推理，降低内存压力"""
        batch_size = max(1, self.settings.batch_page_size)
        all_outputs = []

        for start_page in range(1, total_pages + 1, batch_size):
            end_page = min(start_page + batch_size - 1, total_pages)
            page_range = f"{start_page}-{end_page}"

            # 每批独立推理
            timeout = max(60, self.settings.load_timeout_seconds)
            with self.mm.inference_context(timeout=timeout) as model:
                try:
                    import inspect

                    sig = inspect.signature(model.predict)
                    kwargs = dict(
                        is_ocr=is_ocr,
                        enable_formula=enable_formula,
                        enable_table=enable_table,
                        language=language,
                        page_ranges=page_range,
                    )
                    mv = model_version
                    if mv and "model_version" in sig.parameters:
                        kwargs["model_version"] = mv
                    batch_outputs = model.predict(input_arg, **kwargs)
                except Exception:
                    batch_outputs = model.predict(
                        input_arg,
                        is_ocr=is_ocr,
                        enable_formula=enable_formula,
                        enable_table=enable_table,
                        language=language,
                        page_ranges=page_range,
                    )

            all_outputs.extend(batch_outputs)

        # 保存所有结果
        job_paths.output_dir.mkdir(parents=True, exist_ok=True)
        for res in all_outputs:
            try:
                res.save_to_json(save_path=job_paths.output_dir.as_posix())
            except Exception:
                pass
            try:
                res.save_to_markdown(save_path=job_paths.output_dir.as_posix())
            except Exception:
                pass
