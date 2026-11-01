import asyncio
import logging
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from config import settings
from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import RequestException
from jellyfin_client import jellyfin
from job_queue import queue
from scrapers.nama import session as nama_session
from scrapers.nama.scraper import cookie_jar

log = logging.getLogger("jellygrab.downloader")
log.setLevel(logging.INFO)
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(_h)
    log.propagate = False

CHUNK_SIZE = 1024 * 256  # 256 KiB
PROGRESS_THROTTLE_SEC = 0.5
# Fail a download that receives no data for this long, so a dead connection
# can't hold a download slot forever. No cap on total download time.
STALL_TIMEOUT_SEC = 300

# Jobs past the limit stay "queued" until a running download frees a slot.
_slots = asyncio.Semaphore(settings.max_concurrent_downloads)
# Running download tasks by job id, so a job can be cancelled.
_tasks: dict[str, asyncio.Task] = {}


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
    log.info("job %s queued: %s -> %s", job.id, title, target_path)
    _start(job.id)
    return job.id


def _start(job_id: str) -> None:
    task = asyncio.create_task(_run_download(job_id))
    _tasks[job_id] = task
    task.add_done_callback(lambda _: _tasks.pop(job_id, None))


def cancel(job_id: str) -> bool:
    """Cancel a queued or downloading job's task. False if it has none."""
    task = _tasks.get(job_id)
    if task is None:
        return False
    task.cancel()
    return True


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
) -> tuple[list[str], int]:
    """Fan out one job per episode into `<tv>/<Title (Year)>/Season XX/<file>.mkv`.

    Files keep their original 30nama basename (which already encodes SxxExx),
    so Jellyfin's matcher slots them into the right episode without renaming.

    Episodes are skipped when their target file already exists — a file only
    lands at `target` after a successful download (`.part` is renamed on
    completion), so existence means it's complete — or when a queued/downloading
    job already targets it. Returns the queued job ids and the skipped count.
    """
    season_n = _season_int(season)
    season_dir_name = f"Season {season_n:02d}" if season_n is not None else "Season Unknown"
    base = _series_folder(title, year) / season_dir_name
    base.mkdir(parents=True, exist_ok=True)

    job_ids: list[str] = []
    skipped = 0
    for ep in episodes:
        url = ep.get("url")
        if not url:
            continue
        target = base / _filename_from_url(url)
        if target.exists():
            skipped += 1
            continue
        ep_num = _season_int(ep.get("episode"))
        if season_n is not None and ep_num is not None:
            ep_title = f"{title} S{season_n:02d}E{ep_num:02d}"
        else:
            ep_title = f"{title} (S{season or '?'}E{ep.get('episode') or '?'})"
        job = await queue.create_unless_active(title=ep_title, url=url, target_path=str(target))
        if job is None:
            skipped += 1
            continue
        log.info("job %s queued: %s -> %s", job.id, ep_title, target)
        _start(job.id)
        job_ids.append(job.id)
    return job_ids, skipped


async def _run_download(job_id: str) -> None:
    try:
        async with _slots:
            completed = await _download(job_id)
    except asyncio.CancelledError:
        # Covers jobs cancelled while waiting for a slot, which never reach _download.
        log.info("job %s cancelled", job_id)
        await queue.update(job_id, state="cancelled", speed_bps=0.0)
        raise
    except Exception:
        # Runs as a fire-and-forget task, so nothing else would ever see this.
        log.exception("job %s: download task crashed", job_id)
        raise
    # Refresh after releasing the slot so the next queued job can start. Kept
    # outside the try above so a cancel here can't mark a finished job "cancelled".
    if completed:
        try:
            await jellyfin.refresh_library()
        except Exception as exc:  # noqa: BLE001
            log.warning("job %s: library refresh failed: %s", job_id, exc)
            # Refresh failure should not mark the download itself as failed.
            await queue.update(job_id, error=f"library refresh failed: {exc}")


async def _download(job_id: str) -> bool:
    """Stream the job's file to disk. Returns True if it completed."""
    job = queue.get(job_id)
    if job is None:
        return False
    target = Path(job.target_path)
    tmp = target.with_suffix(target.suffix + ".part")
    log.info("job %s started: %s (%s)", job_id, job.title, job.url)

    try:
        await queue.update(job_id, state="downloading")
        # curl_cffi impersonates Chrome's TLS/JA3 fingerprint so Cloudflare
        # accepts the cookie jar issued to our headless Chromium session.
        # Plain httpx gets bounced even with valid cf_clearance because its
        # TLS handshake doesn't match the browser CF expects.
        # Use the UA that FlareSolverr presented when it solved CF — cf_clearance
        # is partly fingerprint-bound, so the download must replay the same UA.
        headers = {
            "User-Agent": nama_session.get_user_agent(),
            "Referer": settings.nama_base_url + "/",
        }
        async with AsyncSession(impersonate="chrome124") as session:
            resp = await session.get(
                job.url,
                headers=headers,
                cookies=cookie_jar(),
                stream=True,
                allow_redirects=True,
                # For streams curl_cffi treats this as a stall timeout
                # (abort under 1 byte/s for this long), not a total limit.
                timeout=STALL_TIMEOUT_SEC,
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
        log.info("job %s completed: %d bytes -> %s", job_id, downloaded, target)
        return True
    except Exception as exc:  # noqa: BLE001
        # Network errors and HTTP status failures are expected; anything else gets a traceback.
        expected = isinstance(exc, RequestException) or str(exc).startswith("HTTP ")
        log.warning("job %s failed: %s", job_id, exc, exc_info=not expected)
        await queue.update(job_id, state="failed", error=str(exc))
        return False
    finally:
        # No-op after a successful rename; drops the partial file on failure or cancel.
        tmp.unlink(missing_ok=True)
