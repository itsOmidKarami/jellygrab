import asyncio
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from curl_cffi.requests import AsyncSession

from config import settings
from jellyfin_client import jellyfin
from job_queue import queue
from scraper import cookie_jar

CHUNK_SIZE = 1024 * 256  # 256 KiB
PROGRESS_THROTTLE_SEC = 0.5


def _filename_from_url(url: str) -> str:
    name = Path(unquote(urlparse(url).path)).name
    return name or "download.bin"


_FS_UNSAFE = '<>:"/\\|?*'


def _sanitize_folder(name: str) -> str:
    cleaned = "".join("_" if c in _FS_UNSAFE else c for c in name).strip(" .")
    return cleaned or "Untitled"


def _series_folder(title: str, year: str | None) -> Path:
    folder = _sanitize_folder(f"{title} ({year})" if year else title)
    return settings.tv_dir / folder


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


def _season_int(season: str | int | None) -> int | None:
    try:
        return int(str(season).strip())
    except (TypeError, ValueError):
        return None


async def enqueue_series_pack(
    title: str,
    year: str | None,
    season: str | int | None,
    episodes: list[dict],
) -> list[str]:
    """Fan out one job per episode into `<tv>/<Title (Year)>/Season XX/<file>.mkv`.

    Files keep their original 30nama basename (which already encodes SxxExx),
    so Jellyfin's matcher slots them into the right episode without renaming.
    """
    season_n = _season_int(season)
    season_dir_name = f"Season {season_n:02d}" if season_n is not None else "Season Unknown"
    base = _series_folder(title, year) / season_dir_name
    base.mkdir(parents=True, exist_ok=True)

    job_ids: list[str] = []
    for ep in episodes:
        url = ep.get("url")
        if not url:
            continue
        target = base / _filename_from_url(url)
        ep_num = _season_int(ep.get("episode"))
        if season_n is not None and ep_num is not None:
            ep_title = f"{title} S{season_n:02d}E{ep_num:02d}"
        else:
            ep_title = f"{title} (S{season or '?'}E{ep.get('episode') or '?'})"
        job = await queue.create(title=ep_title, url=url, target_path=str(target))
        asyncio.create_task(_run_download(job.id))
        job_ids.append(job.id)
    return job_ids


async def _run_download(job_id: str) -> None:
    job = queue.get(job_id)
    if job is None:
        return
    target = Path(job.target_path)
    tmp = target.with_suffix(target.suffix + ".part")

    try:
        await queue.update(job_id, state="downloading")
        # curl_cffi impersonates Chrome's TLS/JA3 fingerprint so Cloudflare
        # accepts the cookie jar issued to our headless Chromium session.
        # Plain httpx gets bounced even with valid cf_clearance because its
        # TLS handshake doesn't match the browser CF expects.
        headers = {
            "User-Agent": settings.nama_user_agent,
            "Referer": settings.nama_base_url + "/",
        }
        async with AsyncSession(impersonate="chrome124") as session:
            resp = await session.get(
                job.url,
                headers=headers,
                cookies=cookie_jar(),
                stream=True,
                allow_redirects=True,
                timeout=None,
            )
            try:
                if resp.status_code >= 400:
                    raise RuntimeError(f"HTTP {resp.status_code} fetching {job.url}")
                total = int(resp.headers.get("Content-Length", 0)) or None
                await queue.update(job_id, bytes_total=total)

                downloaded = 0
                last_update = 0.0
                last_bytes = 0
                with tmp.open("wb") as fh:
                    async for chunk in resp.aiter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        downloaded += len(chunk)
                        now = time.monotonic()
                        if now - last_update >= PROGRESS_THROTTLE_SEC:
                            speed = (downloaded - last_bytes) / (now - last_update) if last_update else 0
                            await queue.update(job_id, bytes_downloaded=downloaded, speed_bps=speed)
                            last_update = now
                            last_bytes = downloaded
            finally:
                await resp.aclose()

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
