import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import downloader
import keepalive
from scrapers import nama as scraper
from config import settings
from jellyfin_client import jellyfin
from job_queue import queue
from session_state import status as session_status
from version import API_VERSION, BUILD_VERSION


def _ensure_cookies_file() -> None:
    """Create an empty cookies JSON on first boot so users can populate it via the plugin UI."""
    target = settings.nama_cookies_file
    if not target or target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ensure_cookies_file()
    await scraper.startup()
    keepalive_task = asyncio.create_task(keepalive.loop())
    try:
        yield
    finally:
        keepalive_task.cancel()
        try:
            await keepalive_task
        except asyncio.CancelledError:
            pass
        await scraper.shutdown()


app = FastAPI(title="JellyGrab Sidecar", version=BUILD_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class DownloadRequest(BaseModel):
    title: str
    url: str
    kind: str = "unknown"
    year: str | None = None


class SearchHit(BaseModel):
    title: str
    year: str | None
    poster: str | None
    detail_url: str
    kind: str
    in_library: bool
    library_matches: list[dict]


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/api/version")
async def api_version() -> dict:
    return {"api": API_VERSION, "build": BUILD_VERSION}


@app.get("/api/search")
async def api_search(q: str) -> list[dict]:
    if not q.strip():
        raise HTTPException(400, "query 'q' is required")
    results = await scraper.search(q)
    hits: list[dict] = []
    for r in results:
        try:
            matches = await jellyfin.search_library(r.title)
        except Exception:
            matches = []
        hits.append(
            SearchHit(
                **r.to_dict(),
                in_library=bool(matches),
                library_matches=matches,
            ).model_dump()
        )
    return hits


@app.get("/api/options")
async def api_options(detail_url: str) -> list[dict]:
    options = await scraper.get_download_options(detail_url)
    return [o.__dict__ for o in options]


@app.post("/api/download")
async def api_download(req: DownloadRequest) -> dict:
    job_id = await downloader.enqueue(title=req.title, url=req.url, kind=req.kind, year=req.year)
    return {"job_id": job_id}


class EpisodeRef(BaseModel):
    episode: str | None = None
    url: str


class SeriesPackRequest(BaseModel):
    title: str
    year: str | None = None
    season: str | None = None
    episodes: list[EpisodeRef]


@app.post("/api/download/series-pack")
async def api_download_series_pack(req: SeriesPackRequest) -> dict:
    if not req.episodes:
        raise HTTPException(400, "episodes is required")
    job_ids = await downloader.enqueue_series_pack(
        title=req.title,
        year=req.year,
        season=req.season,
        episodes=[ep.model_dump() for ep in req.episodes],
    )
    return {"job_ids": job_ids}


@app.get("/api/status/{job_id}")
async def api_status(job_id: str) -> dict:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job.to_dict()


@app.get("/api/jobs")
async def api_jobs() -> list[dict]:
    return [j.to_dict() for j in queue.list()]


@app.post("/api/jobs/clear")
async def api_jobs_clear() -> dict:
    cleared = await queue.clear_finished()
    return {"cleared": cleared}


@app.get("/api/session-status")
async def api_session_status() -> dict:
    return session_status.to_dict()


class CookieUpdate(BaseModel):
    raw: str | None = None  # full Cookie: header value, e.g. "name=val; name2=val2"
    jar: dict[str, str] | None = None  # alternative: a {name: value} object


def _parse_cookie_header(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            if k:
                out[k] = v.strip()
    return out


@app.post("/api/cookies")
async def api_set_cookies(update: CookieUpdate) -> dict:
    if not settings.nama_cookies_file:
        raise HTTPException(400, "NAMA_COOKIES_FILE is not configured")

    if update.jar:
        jar = {str(k): str(v) for k, v in update.jar.items()}
    elif update.raw:
        jar = _parse_cookie_header(update.raw)
    else:
        raise HTTPException(400, "either 'raw' or 'jar' is required")
    if not jar:
        raise HTTPException(400, "no cookies parsed from input")

    target = settings.nama_cookies_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(jar, indent=2, ensure_ascii=False))
    scraper._cookie_jar.cache_clear()
    await scraper.reseed_cookies()
    return {"ok": True, "cookies": len(jar)}


@app.post("/api/keepalive/run")
async def api_keepalive_run() -> dict:
    """Force a fresh keepalive ping right now (don't wait for the next interval)."""
    try:
        await keepalive._ping_once()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "status": session_status.to_dict()}
    return {"ok": True, "status": session_status.to_dict()}


if settings.plugin_dir.exists():
    app.mount("/plugin", StaticFiles(directory=str(settings.plugin_dir)), name="plugin")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.sidecar_host, port=settings.sidecar_port, reload=False)
