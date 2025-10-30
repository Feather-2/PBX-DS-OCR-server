from __future__ import annotations

"""
DeepSeek-OCR adapter.

This module wraps the DeepSeek-OCR Transformers model to provide a
`predict(input, ...) -> List[Result]` API compatible with the existing
pipeline expectations. It focuses on high-performance single-process
inference with optional GPU acceleration and safe memory-concurrency
controls delegated to ModelManager.

Notes:
- Uses Hugging Face Transformers with `trust_remote_code=True` to access
  the model's `infer` helper.
- PDF inputs are rendered to images via PyMuPDF (fitz) and processed
  page-by-page, honoring `page_ranges` if provided.
- Results expose `markdown`-like structure and implement `save_to_json`
  and `save_to_markdown` used by the pipeline. JSON is aggregated into
  `layout.json` (appending page-wise).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import io
import logging

from PIL import Image

from ..config import Settings

# 常量定义
DEFAULT_DPI = 144
DEFAULT_ZOOM = DEFAULT_DPI / 72.0
IMAGE_QUALITY_JPEG = 85
IMAGE_QUALITY_INFERENCE = 95


def _parse_dtype(name: str):
    try:
        import torch

        m = name.strip().lower()
        if m in {"auto"}:
            # Prefer bfloat16 on CUDA (Ampere/Ada+), else float32 on CPU
            try:
                if torch.cuda.is_available():
                    return torch.bfloat16
            except Exception:
                pass
            return torch.float32
        if m in {"bf16", "bfloat16"}:
            return torch.bfloat16
        if m in {"fp16", "float16", "half"}:
            return torch.float16
        if m in {"fp32", "float32", "full"}:
            return torch.float32
        # default
        return torch.bfloat16
    except Exception:
        return None


def _parse_page_ranges(spec: Optional[str], total_pages: int) -> List[int]:
    """Parse a page range string like "1-3,5,7-8" into 1-based page indexes.
    Out-of-range indices are clamped to [1, total_pages].
    """
    if not spec:
        return list(range(1, total_pages + 1))
    pages: List[int] = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                start = max(1, min(total_pages, int(a)))
                end = max(1, min(total_pages, int(b)))
                if start <= end:
                    pages.extend(range(start, end + 1))
                else:
                    pages.extend(range(end, start + 1))
            except Exception:
                continue
        else:
            try:
                p = max(1, min(total_pages, int(part)))
                pages.append(p)
            except Exception:
                continue
    # De-duplicate but keep order
    seen = set()
    out: List[int] = []
    for p in pages:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out or list(range(1, total_pages + 1))


def _pdf_to_images(path: Path, dpi: int = DEFAULT_DPI, pages: Optional[List[int]] = None) -> List[Image.Image]:
    """Render PDF pages to PIL Images using PyMuPDF (fitz).
    `pages` is 1-based indices to include; if None, include all.
    """
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise RuntimeError("PyMuPDF is required for PDF rendering. Install `PyMuPDF`." ) from e

    images: List[Image.Image] = []
    zoom = dpi / 72.0  # 72 DPI 是 PDF 的标准分辨率
    mat = fitz.Matrix(zoom, zoom)
    with fitz.open(path.as_posix()) as doc:
        total = doc.page_count
        indices = pages or list(range(1, total + 1))
        for p in indices:
            i = max(1, min(total, p)) - 1
            page = doc.load_page(i)
            pm = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.open(io.BytesIO(pm.tobytes("png"))).convert("RGB")
            images.append(img)
    return images


@dataclass
class DSResult:
    page_index: int
    markdown_text: str
    markdown_images: Dict[str, Image.Image]
    raw_json: Dict[str, Any]

    def markdown(self) -> Dict[str, Any]:
        return {
            "markdown_texts": self.markdown_text,
            "markdown_images": self.markdown_images,
        }

    def json(self) -> Dict[str, Any]:
        return {
            "page_index": self.page_index,
            "res": self.raw_json,
        }

    # Compatible save API expected by pipeline
    def save_to_markdown(self, save_path: str):
        # Optional: write per-page markdown if desired. The pipeline already
        # generates a combined full.md, so we keep this a no-op.
        try:
            base = Path(save_path)
            base.mkdir(parents=True, exist_ok=True)
            # Save images into images/ with stable names
            img_out = base / "images"
            img_out.mkdir(parents=True, exist_ok=True)
            idx = 0
            for k, img in self.markdown_images.items():
                p = img_out / f"page_{self.page_index:04d}_{idx:02d}.jpg"
                try:
                    img.convert("RGB").save(p, format="JPEG", quality=IMAGE_QUALITY_JPEG)
                except Exception:
                    pass
                idx += 1
        except Exception:
            pass

    def save_to_json(self, save_path: str):
        """
        Append this page's JSON-like content to a `layout.json` file.
        Structure: { "pages": [ {page_index, res: {...}} ] }
        """
        try:
            base = Path(save_path)
            base.mkdir(parents=True, exist_ok=True)
            jf = base / "layout.json"
            data = {"pages": []}
            if jf.exists():
                try:
                    import json

                    data = json.loads(jf.read_text(encoding="utf-8")) or {"pages": []}
                except Exception:
                    data = {"pages": []}
            data.setdefault("pages", []).append(self.json())
            # atomic write
            import json

            tmp = jf.with_suffix(jf.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp.replace(jf)
        except Exception:
            pass


class DeepSeekOCRModel:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._logger = logging.getLogger("dsocr-service")
        self.runtime_device: str = "cpu"
        self.fallback_reason: Optional[str] = None

        # Initialize Torch device preference early
        if getattr(self.s, "force_cpu", False):
            import os

            os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
            os.environ.setdefault("NVIDIA_VISIBLE_DEVICES", "")

        # Lazy-loaded HF components
        self._tokenizer = None
        self._model = None

        # Cache dtype
        self._dtype = _parse_dtype(getattr(self.s, "ds_dtype", "bfloat16"))

        # Decide device
        self._select_device()

    # Internal helpers
    def _select_device(self):
        try:
            import torch

            if getattr(self.s, "force_cpu", False):
                self.runtime_device = "cpu"
                self._device = torch.device("cpu")
                self._logger.info("runtime device selected: cpu (forced)")
                return
            if torch.cuda.is_available():
                idx = max(0, int(getattr(self.s, "gpu_index", 0)))
                self._device = torch.device(f"cuda:{idx}")
                self.runtime_device = "gpu"
                self._logger.info("runtime device selected: gpu")
            else:
                self._device = torch.device("cpu")
                self.runtime_device = "cpu"
                self._logger.info("runtime device selected: cpu (no cuda)")
        except Exception:
            self._device = None
            self.runtime_device = "unknown"

    def _ensure_loaded(self):
        if self._model is not None and self._tokenizer is not None:
            return
        try:
            from transformers import AutoModel, AutoTokenizer
            import torch

            model_path = getattr(self.s, "ds_model_path", "deepseek-ai/DeepSeek-OCR")
            self._tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

            attn_impl = "flash_attention_2" if getattr(self.s, "ds_use_flash_attn", True) else None
            try:
                if attn_impl:
                    self._model = AutoModel.from_pretrained(
                        model_path,
                        trust_remote_code=True,
                        use_safetensors=True,
                        _attn_implementation=attn_impl,
                    )
                else:
                    self._model = AutoModel.from_pretrained(
                        model_path, trust_remote_code=True, use_safetensors=True
                    )
            except Exception:
                # Fallback without flash-attn
                self._model = AutoModel.from_pretrained(
                    model_path, trust_remote_code=True, use_safetensors=True
                )

            self._model = self._model.eval()
            if self.runtime_device == "gpu":
                self._model = self._model.to(self._device)
                if self._dtype is not None:
                    try:
                        self._model = self._model.to(self._dtype)
                    except Exception:
                        pass
            else:
                # CPU dtype left default
                pass
            self._logger.info("DeepSeek-OCR model loaded: %s", model_path)
        except Exception as e:
            self.fallback_reason = str(e)
            raise

    # Public API expected by pipeline
    def predict(
        self,
        input_arg: str,
        *,
        is_ocr: bool = True,
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        page_ranges: Optional[str] = None,
        # model_version ignored; kept for compatibility with callers using inspect
        model_version: Optional[str] = None,
        # extra arguments ignored by DS; accepted for compatibility
        **_: Any,
    ) -> List[DSResult]:
        """
        Run inference on an image or a PDF.
        Returns a list of DSResult (one per image or page).
        """
        self._ensure_loaded()

        path = Path(input_arg)
        if not path.exists():
            raise FileNotFoundError(f"Input not found: {path}")

        # Build prompt
        prompt = self._build_prompt(is_ocr=is_ocr, enable_formula=enable_formula, enable_table=enable_table)

        # Collect images
        images: List[Tuple[int, Image.Image]] = []
        if path.suffix.lower() == ".pdf":
            # Render PDF into images
            try:
                import pypdf  # noqa: F401
            except Exception:
                pass
            # Get page count via fitz to handle encrypted leniently
            try:
                import fitz

                with fitz.open(path.as_posix()) as doc:
                    total = doc.page_count
            except Exception:
                total = 0
            pages = _parse_page_ranges(page_ranges, total) if total > 0 else None
            pil_images = _pdf_to_images(path, dpi=144, pages=pages)
            # Map 1-based page indexes aligning with pages list when provided
            if pages:
                images = list(zip(pages, pil_images))
            else:
                images = [(i + 1, im) for i, im in enumerate(pil_images)]
        else:
            img = Image.open(path).convert("RGB")
            images = [(1, img)]

        # Inference per image
        results: List[DSResult] = []
        for page_idx, img in images:
            res = self._infer_one(img, prompt, page_index=page_idx)
            results.append(res)
        return results

    # Internal inference
    def _infer_one(self, image: Image.Image, prompt: str, *, page_index: int) -> DSResult:
        """Call model.infer(tokenizer, ...) and parse to DSResult."""
        # The DS model implements `.infer(tokenizer, prompt, image_file|image, ...)` when using trust_remote_code.
        # We convert PIL image to a temporary file in-memory to avoid FS churn.
        # If the model supports directly passing PIL images, we can adapt later.
        import tempfile
        import os

        tmp_dir = None
        tmp_img_path = None
        try:
            tmp_dir = tempfile.mkdtemp(prefix="dsocr_")
            tmp_img_path = os.path.join(tmp_dir, "input.jpg")
            image.convert("RGB").save(tmp_img_path, format="JPEG", quality=IMAGE_QUALITY_INFERENCE)

            # Inference
            infer_kwargs = dict(
                prompt=prompt,
                image_file=tmp_img_path,
                output_path=tmp_dir,  # we do not rely on saved files but some models require it
                base_size=int(getattr(self.s, "ds_base_size", 1024)),
                image_size=int(getattr(self.s, "ds_image_size", 640)),
                crop_mode=bool(getattr(self.s, "ds_crop_mode", True)),
                save_results=False,
                test_compress=False,
            )
            out = self._model.infer(self._tokenizer, **infer_kwargs)  # type: ignore[attr-defined]

            markdown_text, markdown_images, raw_json = self._parse_output(out)
            return DSResult(
                page_index=page_index,
                markdown_text=markdown_text,
                markdown_images=markdown_images,
                raw_json=raw_json,
            )
        finally:
            # cleanup temp dir (使用 shutil.rmtree 以确保完全清理)
            if tmp_dir:
                try:
                    import shutil
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass

    def _build_prompt(self, *, is_ocr: bool, enable_formula: bool, enable_table: bool) -> str:
        override = getattr(self.s, "ds_prompt_override", None)
        if isinstance(override, str) and override.strip():
            return override.strip()
        # Default prompt optimized for document markdown conversion
        # Optionally switch to more general OCR if requested.
        if is_ocr:
            return "<image>\n<|grounding|>Convert the document to markdown."
        else:
            return "<image>\nFree OCR."

    def _parse_output(self, out: Any) -> Tuple[str, Dict[str, Image.Image], Dict[str, Any]]:
        """Try to normalize infer() outputs to (markdown_text, images, json).
        Be defensive: handle string, dict, or objects with attributes.
        """
        text = ""
        images: Dict[str, Image.Image] = {}
        raw: Dict[str, Any] = {}
        try:
            # If out is a dict-like
            if isinstance(out, dict):
                raw = dict(out)
                # Common keys from DeepSeek examples
                if isinstance(out.get("markdown_texts"), str):
                    text = out["markdown_texts"]
                elif isinstance(out.get("markdown_text"), str):
                    text = out["markdown_text"]
                # Images could be already PILs
                mi = out.get("markdown_images")
                if isinstance(mi, dict):
                    for k, v in mi.items():
                        try:
                            if isinstance(v, Image.Image):
                                images[str(k)] = v
                        except Exception:
                            continue
            # If out has attributes
            elif hasattr(out, "markdown") or hasattr(out, "markdown_texts"):
                try:
                    md = getattr(out, "markdown", None)
                    if callable(md):
                        md = md()
                except Exception:
                    md = None
                if isinstance(md, dict):
                    text = md.get("markdown_texts") or md.get("markdown_text") or ""
                    mi = md.get("markdown_images") or {}
                    if isinstance(mi, dict):
                        for k, v in mi.items():
                            if isinstance(v, Image.Image):
                                images[str(k)] = v
                else:
                    # Fallback attributes
                    val = getattr(out, "markdown_texts", None) or getattr(out, "markdown_text", None)
                    if isinstance(val, str):
                        text = val
            # If out is a simple string
            elif isinstance(out, str):
                text = out
            # Last resort: string conversion
            if not text:
                try:
                    text = str(out)
                except Exception:
                    text = ""
        except Exception:
            pass
        # raw json: include text at least
        if not raw:
            raw = {"text": text}
        return text or "", images, raw
