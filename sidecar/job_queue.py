import asyncio
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Literal

JobState = Literal["queued", "downloading", "completed", "failed", "cancelled"]


@dataclass
class JobStatus:
    id: str
    title: str
    url: str
    target_path: str
    state: JobState = "queued"
    bytes_downloaded: int = 0
    bytes_total: int | None = None
    progress: float = 0.0
    speed_bps: float = 0.0
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class JobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, JobStatus] = {}
        self._lock = asyncio.Lock()

    async def create(self, title: str, url: str, target_path: str) -> JobStatus:
        async with self._lock:
            job = JobStatus(
                id=uuid.uuid4().hex,
                title=title,
                url=url,
                target_path=target_path,
            )
            self._jobs[job.id] = job
            return job

    async def update(self, job_id: str, **fields) -> JobStatus | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for key, value in fields.items():
                setattr(job, key, value)
            if job.bytes_total:
                job.progress = job.bytes_downloaded / job.bytes_total
            job.updated_at = time.time()
            return job

    def get(self, job_id: str) -> JobStatus | None:
        return self._jobs.get(job_id)

    def list(self) -> list[JobStatus]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    async def clear_finished(self) -> int:
        async with self._lock:
            terminal = {"completed", "failed", "cancelled"}
            to_drop = [jid for jid, j in self._jobs.items() if j.state in terminal]
            for jid in to_drop:
                del self._jobs[jid]
            return len(to_drop)


queue = JobQueue()
