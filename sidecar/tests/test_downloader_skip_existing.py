"""Tests for skip-existing behavior in enqueue_series_pack.

A file only lands at its target after a successful download (`.part` is
renamed on completion), so a target that already exists means the episode
is complete — it must be skipped, not re-queued. Likewise, an episode that
already has a queued/downloading job must not get a second one: both would
stream into the same `.part` file and corrupt it.
"""

import dataclasses

import downloader
import pytest
from downloader import enqueue_series_pack
from fastapi.testclient import TestClient
from job_queue import JobQueue
from main import app

EP1 = {"url": "https://cdn/Show.S01E01.mkv", "episode": "1"}
EP2 = {"url": "https://cdn/Show.S01E02.mkv", "episode": "2"}


@pytest.fixture
def season_dir(tmp_path, monkeypatch):
    """Point the TV root at tmp_path, isolate the job queue, and stub out the
    network download. Returns the season folder episodes land in."""
    monkeypatch.setattr(downloader, "settings", dataclasses.replace(downloader.settings, tv_dir=tmp_path))
    monkeypatch.setattr(downloader, "queue", JobQueue())

    async def _noop_download(job_id: str) -> None:
        return None

    monkeypatch.setattr(downloader, "_run_download", _noop_download)
    return tmp_path / "Show (2024)" / "Season 01"


def _touch(season_dir, ep):
    target = season_dir / ep["url"].rsplit("/", 1)[-1]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()


async def test_queues_episode_when_target_missing(season_dir):
    job_ids, skipped = await enqueue_series_pack("Show", "2024", "1", [EP1])

    assert len(job_ids) == 1
    assert skipped == 0
    assert [j.url for j in downloader.queue.list()] == [EP1["url"]]


async def test_skips_episode_whose_target_exists(season_dir):
    _touch(season_dir, EP1)

    job_ids, skipped = await enqueue_series_pack("Show", "2024", "1", [EP1])

    assert job_ids == []
    assert skipped == 1
    assert downloader.queue.list() == []


async def test_mixed_pack_skips_only_existing(season_dir):
    _touch(season_dir, EP1)

    job_ids, skipped = await enqueue_series_pack("Show", "2024", "1", [EP1, EP2])

    assert len(job_ids) == 1
    assert skipped == 1
    assert [j.url for j in downloader.queue.list()] == [EP2["url"]]


@pytest.mark.parametrize("state", ["queued", "downloading"])
async def test_skips_episode_already_in_flight(season_dir, state):
    (first,), _ = await enqueue_series_pack("Show", "2024", "1", [EP1])
    await downloader.queue.update(first, state=state)

    job_ids, skipped = await enqueue_series_pack("Show", "2024", "1", [EP1, EP2])

    assert len(job_ids) == 1
    assert skipped == 1
    assert sorted(j.url for j in downloader.queue.list()) == [EP1["url"], EP2["url"]]


@pytest.mark.parametrize("state", ["failed", "cancelled"])
async def test_requeues_episode_after_inactive_job(season_dir, state):
    (first,), _ = await enqueue_series_pack("Show", "2024", "1", [EP1])
    await downloader.queue.update(first, state=state)

    job_ids, skipped = await enqueue_series_pack("Show", "2024", "1", [EP1])

    assert len(job_ids) == 1
    assert job_ids[0] != first
    assert skipped == 0


def test_series_pack_endpoint_reports_skipped(season_dir):
    _touch(season_dir, EP1)

    resp = TestClient(app).post(
        "/api/download/series-pack",
        json={"title": "Show", "year": "2024", "season": "1", "episodes": [EP1, EP2]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["job_ids"]) == 1
    assert body["skipped"] == 1
