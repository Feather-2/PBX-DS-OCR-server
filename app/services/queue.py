from __future__ import annotations

"""
Lightweight job queue:
- In-memory queue + worker threads
- Persist job status via storage (atomic writes)
"""

import queue
import threading
import time
from typing import Dict, Optional

from ..config import Settings, load_settings
from ..schemas import JobStatus
from ..storage import save_status
from .pipeline import DocumentPipeline
from ..domain.job import Job
from ..integrations.publisher import Publisher
from ..monitoring import metrics as app_metrics


class JobQueue:
    def __init__(self, pipeline: DocumentPipeline, settings: Optional[Settings] = None):
        self.settings = settings or load_settings()
        self.pipeline = pipeline
        # 使用有界队列防止内存无限增长
        max_size = max(1, self.settings.max_queue_size)
        self._q: "queue.Queue[Optional[Job]]" = queue.Queue(maxsize=max_size)
        self._jobs: Dict[str, Job] = {}
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._publisher = Publisher(self.settings)

    def submit(self, job: Job) -> bool:
        """
        提交任务到队列。
        返回 True 表示成功入队，False 表示队列已满。
        """
        with self._lock:
            self._jobs[job.task_id] = job
        job.dump_status()
        try:
            # 非阻塞提交，如果队列满则立即返回 False
            self._q.put(job, block=False)
            try:
                app_metrics.task_submitted()
                app_metrics.update_queue(self._q.qsize(), self.running_workers())
            except Exception:
                pass
            return True
        except queue.Full:
            return False

    def get(self, task_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(task_id)

    def start(self):
        for i in range(max(1, self.settings.max_workers)):
            t = threading.Thread(target=self._worker, name=f"worker-{i}", daemon=True)
            t.start()
            self._workers.append(t)

    def stop(self):
        self._stop.set()
        # Wake up workers so they can exit
        for _ in self._workers:
            self._q.put(None)
        for t in self._workers:
            t.join(timeout=1.0)

    def _worker(self):
        while not self._stop.is_set():
            try:
                job = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            if job is None:
                # Exit signal
                continue
            # Execute
            job.status = JobStatus.processing
            job.started_at = time.time()
            job.dump_status()
            try:
                self.pipeline.run(
                    job.paths.input_file.as_posix()
                    if not job.options.get("is_url")
                    else job.options["url"],
                    job.paths,
                    is_url=bool(job.options.get("is_url")),
                    bbox=bool(job.options.get("bbox", True)),
                    pack=bool(job.options.get("pack_zip", True)),
                    is_ocr=bool(job.options.get("is_ocr", True)),
                    enable_formula=bool(job.options.get("enable_formula", True)),
                    enable_table=bool(job.options.get("enable_table", True)),
                    language=str(job.options.get("language", "ch")),
                    page_ranges=job.options.get("page_ranges"),
                    model_version=job.options.get("model_version"),
                )
                job.status = JobStatus.succeeded
                try:
                    app_metrics.task_succeeded()
                except Exception:
                    pass
                # Optional auto publish
                if self.settings.auto_publish:
                    try:
                        info = self._publisher.publish(job.task_id, job.paths)
                        data = job.to_dict()
                        data["published"] = info
                        save_status(job.paths, data)
                    except Exception:
                        # Publishing failure should not break core result
                        pass
            except Exception as e:
                job.status = JobStatus.failed
                job.message = str(e)
                try:
                    app_metrics.task_failed()
                except Exception:
                    pass
            finally:
                job.finished_at = time.time()
                job.dump_status()
                self._q.task_done()
                try:
                    app_metrics.update_queue(self._q.qsize(), self.running_workers())
                except Exception:
                    pass

    def queue_size(self) -> int:
        return self._q.qsize()

    def is_queue_full(self) -> bool:
        """检查队列是否已满"""
        return self._q.full()

    def queue_capacity(self) -> int:
        """返回队列最大容量"""
        return self.settings.max_queue_size

    def running_workers(self) -> int:
        return sum(1 for t in self._workers if t.is_alive())
