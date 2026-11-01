"""MAX_CONCURRENT_DOWNLOADS caps how many downloads stream at once."""

import asyncio
import dataclasses

import downloader
from job_queue import JobQueue


async def test_running_downloads_never_exceed_limit(monkeypatch):
    monkeypatch.setattr(downloader, "_slots", asyncio.Semaphore(2))
    running = peak = 0
    finished = []

    async def _fake_download(job_id: str) -> bool:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        try:
            await asyncio.sleep(0.01)
            if job_id == "0":
                raise RuntimeError("boom")  # a failing job must still free its slot
            finished.append(job_id)
            return False
        finally:
            running -= 1

    monkeypatch.setattr(downloader, "_download", _fake_download)

    results = await asyncio.wait_for(
        asyncio.gather(*(downloader._run_download(str(i)) for i in range(5)), return_exceptions=True),
        timeout=2,
    )

    assert peak == 2
    assert isinstance(results[0], RuntimeError)
    assert sorted(finished) == ["1", "2", "3", "4"]


async def test_series_pack_downloads_wait_for_a_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader, "settings", dataclasses.replace(downloader.settings, tv_dir=tmp_path))
    monkeypatch.setattr(downloader, "queue", JobQueue())
    monkeypatch.setattr(downloader, "_slots", asyncio.Semaphore(2))
    release = asyncio.Event()
    running = 0

    async def _fake_download(job_id: str) -> bool:
        nonlocal running
        running += 1
        await release.wait()
        running -= 1
        return False

    monkeypatch.setattr(downloader, "_download", _fake_download)

    episodes = [{"url": f"https://cdn/Show.S01E0{n}.mkv", "episode": str(n)} for n in range(1, 6)]
    job_ids, _ = await downloader.enqueue_series_pack("Show", "2024", "1", episodes)
    for _ in range(5):
        await asyncio.sleep(0)

    assert len(job_ids) == 5
    assert running == 2

    release.set()
    for _ in range(10):
        await asyncio.sleep(0)
    assert running == 0
