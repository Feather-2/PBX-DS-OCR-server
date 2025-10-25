from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Dict, Optional

from ..schemas import JobStatus
from ..storage import JobPaths, save_status


STATUS_FILE = "job_status.json"


@dataclass
class Job:
    task_id: str
    paths: JobPaths
    options: Dict[str, Any]
    status: JobStatus = JobStatus.queued
    queued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "message": self.message,
        }

    def dump_status(self) -> None:
        save_status(self.paths, self.to_dict())

