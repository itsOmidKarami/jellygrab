"""POST /api/jobs/{id}/cancel stops queued and running downloads."""

import asyncio
import dataclasses

import downloader
import main
import pytest
from fastapi import HTTPException
from job_queue import JobQueue


async def _settle():
    for _ in range(10):
        await asyncio.sleep(0)


@pytest.fixture
def started(tmp_path, monkeypatch):
    """One download slot; a fake _download that blocks until `release` is set."""
    q = JobQueue()
    monkeypatch.setattr(downloader, "settings", dataclasses.replace(downloader.settings, movies_dir=tmp_path))
    monkeypatch.setattr(downloader, "queue", q)
    monkeypatch.setattr(main, "queue", q)
    monkeypatch.setattr(downloader, "_slots", asyncio.Semaphore(1))
    monkeypatch.setattr(downloader, "_tasks", {})
    release = asyncio.Event()
    started: list[str] = []

    async def _fake_download(job_id: str) -> bool:
        started.append(job_id)
        await q.update(job_id, state="downloading")
        await release.wait()
        await q.update(job_id, state="completed")
        return False

    monkeypatch.setattr(downloader, "_download", _fake_download)
    return q, release, started


async def test_cancel_queued_then_running_job(started):
    q, release, ran = started
    first = await downloader.enqueue("A", "https://cdn/A.mkv", kind="movie")
    second = await downloader.enqueue("B", "https://cdn/B.mkv", kind="movie")
    third = await downloader.enqueue("C", "https://cdn/C.mkv", kind="movie")
    await _settle()
    assert ran == [first]
    assert q.get(second).state == "queued"

    # Queued job: cancelled without ever starting.
    await main.api_job_cancel(second)
    await _settle()
    assert q.get(second).state == "cancelled"

    # Running job: cancelled, and its slot goes to the next queued job.
    await main.api_job_cancel(first)
    await _settle()
    assert q.get(first).state == "cancelled"
    assert ran == [first, third]
    assert downloader._tasks.keys() == {third}

    release.set()
    await _settle()
    assert q.get(third).state == "completed"
    assert downloader._tasks == {}


async def test_cancel_unknown_job_is_404(started):
    with pytest.raises(HTTPException) as exc:
        await main.api_job_cancel("nope")
    assert exc.value.status_code == 404


async def test_cancel_finished_job_is_409(started):
    q, release, _ = started
    release.set()
    job_id = await downloader.enqueue("A", "https://cdn/A.mkv", kind="movie")
    await _settle()
    assert q.get(job_id).state == "completed"

    with pytest.raises(HTTPException) as exc:
        await main.api_job_cancel(job_id)
    assert exc.value.status_code == 409


async def test_cancel_mid_stream_deletes_part_file(tmp_path, monkeypatch):
    q = JobQueue()
    monkeypatch.setattr(downloader, "queue", q)
    monkeypatch.setattr(downloader, "cookie_jar", lambda: {})
    target = tmp_path / "A.mkv"
    job = await q.create(title="A", url="https://cdn/A.mkv", target_path=str(target))
    streaming = asyncio.Event()

    class _Resp:
        status_code = 200
        headers = {"Content-Length": "100"}

        async def aiter_content(self, chunk_size):
            yield b"x" * 10
            streaming.set()
            await asyncio.Event().wait()  # stall forever
            yield b""

        async def aclose(self):
            pass

    class _Session:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def get(self, *_, **__):
            return _Resp()

    monkeypatch.setattr(downloader, "AsyncSession", _Session)

    task = asyncio.create_task(downloader._run_download(job.id))
    await streaming.wait()
    assert (tmp_path / "A.mkv.part").exists()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert q.get(job.id).state == "cancelled"
    assert not (tmp_path / "A.mkv.part").exists()
    assert not target.exists()
