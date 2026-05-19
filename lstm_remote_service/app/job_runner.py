from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .config import settings
from .forecast import run_lstm_job
from .schemas import ForecastRequest, JobStatusResponse


class JobRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._pool = ThreadPoolExecutor(max_workers=max(1, settings.max_workers))

    def submit(self, payload: ForecastRequest) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "submitted_at": datetime.now(timezone.utc),
                "started_at": None,
                "finished_at": None,
                "error": None,
                "result": None,
            }
        self._pool.submit(self._run_job, job_id, payload)
        return job_id

    def _run_job(self, job_id: str, payload: ForecastRequest):
        with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id]["status"] = "running"
            self._jobs[job_id]["started_at"] = datetime.now(timezone.utc)

        try:
            result = run_lstm_job(payload)
            with self._lock:
                if job_id in self._jobs:
                    self._jobs[job_id]["status"] = "completed"
                    self._jobs[job_id]["finished_at"] = datetime.now(timezone.utc)
                    self._jobs[job_id]["result"] = result
        except Exception as exc:
            with self._lock:
                if job_id in self._jobs:
                    self._jobs[job_id]["status"] = "failed"
                    self._jobs[job_id]["finished_at"] = datetime.now(timezone.utc)
                    self._jobs[job_id]["error"] = str(exc)

    def get(self, job_id: str) -> JobStatusResponse | None:
        with self._lock:
            raw = self._jobs.get(job_id)
            if raw is None:
                return None
            return JobStatusResponse(**raw)


registry = JobRegistry()
