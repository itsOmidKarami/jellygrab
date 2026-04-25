import asyncio
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from config import settings
from jellyfin_client import jellyfin
from job_queue import queue

CHUNK_SIZE = 1024 * 256  # 256 KiB
PROGRESS_THROTTLE_SEC = 0.5


def _filename_from_url(url: str) -> str:
    name = Path(unquote(urlparse(url).path)).name
    return name or "download.bin"


async def enqueue(title: str, url: str, subdir: str = "") -> str:
    target_dir = settings.download_dir / subdir if subdir else settings.download_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / _filename_from_url(url)
    job = await queue.create(title=title, url=url, target_path=str(target_path))
    asyncio.create_task(_run_download(job.id))
    return job.id


async def _run_download(job_id: str) -> None:
    job = queue.get(job_id)
    if job is None:
        return
    target = Path(job.target_path)
    tmp = target.with_suffix(target.suffix + ".part")

    try:
        await queue.update(job_id, state="downloading")
        headers = {"User-Agent": settings.nama_user_agent}
        async with httpx.AsyncClient(follow_redirects=True, timeout=None, headers=headers) as client:
            async with client.stream("GET", job.url) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0)) or None
                await queue.update(job_id, bytes_total=total)

                downloaded = 0
                last_update = 0.0
                last_bytes = 0
                with tmp.open("wb") as fh:
                    async for chunk in resp.aiter_bytes(CHUNK_SIZE):
                        fh.write(chunk)
                        downloaded += len(chunk)
                        now = time.monotonic()
                        if now - last_update >= PROGRESS_THROTTLE_SEC:
                            speed = (downloaded - last_bytes) / (now - last_update) if last_update else 0
                            await queue.update(job_id, bytes_downloaded=downloaded, speed_bps=speed)
                            last_update = now
                            last_bytes = downloaded

        tmp.replace(target)
        await queue.update(job_id, bytes_downloaded=downloaded, state="completed", speed_bps=0.0)
        try:
            await jellyfin.refresh_library()
        except Exception as exc:
            # Refresh failure should not mark the download itself as failed.
            await queue.update(job_id, error=f"library refresh failed: {exc}")
    except Exception as exc:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        await queue.update(job_id, state="failed", error=str(exc))
