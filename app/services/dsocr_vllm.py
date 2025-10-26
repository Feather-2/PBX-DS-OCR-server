from __future__ import annotations

"""
DeepSeek-OCR vLLM adapter.

Optional high-throughput backend using vLLM. Requires a vLLM version
that includes DeepSeek-OCR support (nightly per official docs at time
of writing). This adapter exposes a predict() API compatible with the
pipeline, returning a list of DSResult (one per page/image).

If vLLM is unavailable, import will fail at runtime and the error will
be surfaced via ModelManager fallback_reason.
"""

from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import logging

from PIL import Image

from ..config import Settings
from .dsocr_model import DSResult, _parse_page_ranges, _pdf_to_images


class DeepSeekOCRVLLM:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._logger = logging.getLogger("dsocr-service")
        self.runtime_device = "gpu"  # vLLM typically runs on GPU; leave as hint
        self.fallback_reason: Optional[str] = None

        # Lazy create LLM
        self._llm = None
        self._sampling = None
        self._init_vllm()

    def _init_vllm(self):
        try:
            # Ensure CUDA is initialized in a spawned subprocess, not in a forked one
            try:
                import multiprocessing as _mp
                if _mp.get_start_method(allow_none=True) != "spawn":
                    _mp.set_start_method("spawn", force=True)
            except Exception:
                pass

            from vllm import LLM, SamplingParams
            # NGram logits processor is recommended by DS-OCR
            try:
                from vllm.model_executor.models.deepseek_ocr import (
                    NGramPerReqLogitsProcessor,
                )
                logits_procs = [NGramPerReqLogitsProcessor]
            except Exception:
                logits_procs = []

            self._llm = LLM(
                model=self.s.ds_model_path,
                enable_prefix_caching=bool(self.s.ds_vllm_enable_prefix_caching),
                mm_processor_cache_gb=int(self.s.ds_vllm_mm_processor_cache_gb),
                logits_processors=logits_procs if logits_procs else None,
            )

            whitelist_ids: Optional[set[int]] = None
            try:
                if isinstance(self.s.ds_vllm_whitelist_token_ids, str) and self.s.ds_vllm_whitelist_token_ids.strip():
                    whitelist_ids = set(
                        int(x.strip())
                        for x in self.s.ds_vllm_whitelist_token_ids.split(",")
                        if x.strip().isdigit()
                    )
            except Exception:
                whitelist_ids = None

            self._sampling = SamplingParams(
                temperature=float(self.s.ds_vllm_temperature),
                max_tokens=int(self.s.ds_vllm_max_tokens),
                extra_args=dict(
                    ngram_size=int(self.s.ds_vllm_ngram_size),
                    window_size=int(self.s.ds_vllm_window_size),
                    whitelist_token_ids=whitelist_ids or {128821, 128822},
                ),
                skip_special_tokens=False,
            )
            self._logger.info("vLLM initialized for model: %s", self.s.ds_model_path)
        except Exception as e:
            self.fallback_reason = str(e)
            raise

    def _build_prompt(self, *, is_ocr: bool, enable_formula: bool, enable_table: bool) -> str:
        override = getattr(self.s, "ds_prompt_override", None)
        if isinstance(override, str) and override.strip():
            return override.strip()
        return "<image>\n<|grounding|>Convert the document to markdown." if is_ocr else "<image>\nFree OCR."

    def predict(
        self,
        input_arg: str,
        *,
        is_ocr: bool = True,
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        page_ranges: Optional[str] = None,
        model_version: Optional[str] = None,
        **_: Any,
    ) -> List[DSResult]:
        path = Path(input_arg)
        if not path.exists():
            raise FileNotFoundError(f"Input not found: {path}")

        prompt = self._build_prompt(
            is_ocr=is_ocr, enable_formula=enable_formula, enable_table=enable_table
        )

        # Prepare images
        items: List[Tuple[int, Image.Image]] = []
        if path.suffix.lower() == ".pdf":
            try:
                import fitz

                with fitz.open(path.as_posix()) as doc:
                    total = doc.page_count
            except Exception:
                total = 0
            pages = _parse_page_ranges(page_ranges, total) if total > 0 else None
            pil_images = _pdf_to_images(path, dpi=144, pages=pages)
            if pages:
                items = list(zip(pages, pil_images))
            else:
                items = [(i + 1, im) for i, im in enumerate(pil_images)]
        else:
            items = [(1, Image.open(path).convert("RGB"))]

        # Batch through vLLM
        model_inputs = [
            {"prompt": prompt, "multi_modal_data": {"image": im}} for _, im in items
        ]
        outputs = self._llm.generate(model_inputs, self._sampling)

        results: List[DSResult] = []
        for (page_idx, _), out in zip(items, outputs):
            try:
                text = out.outputs[0].text if out and out.outputs else ""
            except Exception:
                text = ""
            if not text:
                try:
                    text = str(out)
                except Exception:
                    text = ""
            results.append(
                DSResult(
                    page_index=page_idx,
                    markdown_text=text,
                    markdown_images={},
                    raw_json={"text": text},
                )
            )
        return results
