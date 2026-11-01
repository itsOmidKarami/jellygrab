"""MAX_CONCURRENT_DOWNLOADS caps how many downloads stream at once."""

import asyncio

import downloader


async def test_running_downloads_never_exceed_limit(monkeypatch):
    monkeypatch.setattr(downloader, "_slots", asyncio.Semaphore(2))
    running = peak = 0

    async def _fake_download(job_id: str) -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1

    monkeypatch.setattr(downloader, "_download", _fake_download)

    await asyncio.gather(*(downloader._run_download(str(i)) for i in range(5)))

    assert peak == 2
