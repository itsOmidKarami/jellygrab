"""Download failures must reach the container logs, not just the job's error field."""

import logging

import downloader
from job_queue import JobQueue


class _FailingSession:
    def __init__(self, **_):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, *_, **__):
        raise ValueError("disk on fire")


async def test_failed_download_is_logged_with_traceback(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(downloader, "queue", JobQueue())
    monkeypatch.setattr(downloader, "AsyncSession", _FailingSession)
    monkeypatch.setattr(downloader, "cookie_jar", lambda: {})
    downloader.log.addHandler(caplog.handler)
    try:
        job = await downloader.queue.create(
            title="Movie", url="https://cdn/Movie.mkv", target_path=str(tmp_path / "Movie.mkv")
        )
        with caplog.at_level(logging.INFO, logger="jellygrab.downloader"):
            assert await downloader._download(job.id) is False
    finally:
        downloader.log.removeHandler(caplog.handler)

    failed = [r for r in caplog.records if "failed" in r.getMessage()]
    assert len(failed) == 1
    assert failed[0].levelno == logging.WARNING
    assert "disk on fire" in failed[0].getMessage()
    assert failed[0].exc_info is not None  # unexpected error -> traceback
    assert downloader.queue.get(job.id).state == "failed"
