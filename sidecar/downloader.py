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


_FS_UNSAFE = '<>:"/\\|?*'


def _sanitize_folder(name: str) -> str:
    cleaned = "".join("_" if c in _FS_UNSAFE else c for c in name).strip(" .")
    return cleaned or "Untitled"


def _resolve_target(title: str, url: str, kind: str, year: str | None) -> Path:
    """Pick the root by content kind and place the file under a per-item folder.

    Why: Jellyfin uses folder paths as part of its matcher, so a flat
    `/media/downloads/Foo.mkv` ends up tagged with the word "downloads". Routing
    movies and series into their own roots — and giving each item its own
    `Title (Year)/` folder — matches Jellyfin's expected layout.
    """
    if kind == "movie":
        root = settings.movies_dir
    elif kind == "series":
        root = settings.tv_dir
    else:
        root = settings.download_dir

    folder = _sanitize_folder(f"{title} ({year})" if year else title)
    return root / folder / _filename_from_url(url)


async def enqueue(title: str, url: str, kind: str = "unknown", year: str | None = None) -> str:
    target_path = _resolve_target(title, url, kind, year)
    target_path.parent.mkdir(parents=True, exist_ok=True)
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
