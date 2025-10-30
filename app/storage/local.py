from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Iterable


@dataclass
class JobPaths:
    root: Path
    input_file: Path
    output_dir: Path
    images_dir: Path
    md_file: Path
    json_file: Path
    zip_file: Path


def init_storage(storage_root: str) -> Path:
    root = Path(storage_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "tmp").mkdir(parents=True, exist_ok=True)
    return root


def new_job(storage_root: str, filename: str) -> tuple[str, JobPaths]:
    job_id = str(uuid.uuid4())
    job_root = Path(storage_root) / job_id
    job_root.mkdir(parents=True, exist_ok=True)
    # Allow only safe suffixes; default to .pdf
    ext = Path(filename).suffix.lower()
    safe_exts = {".pdf", ".png", ".jpg", ".jpeg"}
    if ext not in safe_exts:
        ext = ".pdf"
    input_file = job_root / f"input{ext}"
    output_dir = job_root / "output"
    images_dir = output_dir / "images"
    md_file = output_dir / "full.md"
    json_file = output_dir / "layout.json"
    zip_file = job_root / "result.zip"
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    return job_id, JobPaths(
        root=job_root,
        input_file=input_file,
        output_dir=output_dir,
        images_dir=images_dir,
        md_file=md_file,
        json_file=json_file,
        zip_file=zip_file,
    )


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data):
    """Atomically write JSON to avoid partial reads."""
    # 检查是否需要写入（避免不必要的磁盘操作）
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing == data:
                return  # 内容相同，跳过写入
        except Exception:
            # 如果读取失败，继续写入
            pass

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_stream(path: Path, chunks: Iterable[bytes]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        for c in chunks:
            if not c:
                continue
            f.write(c)


def save_status(paths: JobPaths, data: dict):
    """Atomically write job status to job_status.json under the job root."""
    write_json(paths.root / "job_status.json", data)


def pack_zip(paths: JobPaths):
    """
    Pack only the output directory (md/json/images) into a zip archive.
    The zip top-level contains full.md, layout.json, and images/ directly.
    """
    base_name = str(paths.zip_file.with_suffix(""))
    if paths.zip_file.exists():
        paths.zip_file.unlink()
    # Create archive with output_dir content at top-level
    shutil.make_archive(base_name, "zip", root_dir=paths.output_dir, base_dir=".")
    return paths.zip_file


def cleanup_old_jobs(storage_root: str, max_retention: int = 1000):
    root = Path(storage_root)
    subdirs = [p for p in root.iterdir() if p.is_dir() and p.name not in {"tmp"}]
    subdirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for p in subdirs[max_retention:]:
        shutil.rmtree(p, ignore_errors=True)


def get_job_paths(storage_root: str, task_id: str) -> JobPaths:
    job_root = Path(storage_root) / task_id
    return JobPaths(
        root=job_root,
        input_file=next(
            (
                p
                for p in [
                    job_root / "input.pdf",
                    job_root / "input.png",
                    job_root / "input.jpg",
                    job_root / "input.jpeg",
                ]
                if p.exists()
            ),
            job_root / "input.pdf",
        ),
        output_dir=job_root / "output",
        images_dir=job_root / "output" / "images",
        md_file=job_root / "output" / "full.md",
        json_file=job_root / "output" / "layout.json",
        zip_file=job_root / "result.zip",
    )


def load_status(storage_root: str, task_id: str) -> Optional[dict]:
    status_file = Path(storage_root) / task_id / "job_status.json"
    return read_json(status_file)

