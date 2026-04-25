from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import downloader
import scraper
from config import settings
from jellyfin_client import jellyfin
from job_queue import queue


@asynccontextmanager
async def lifespan(_: FastAPI):
    await scraper.startup()
    try:
        yield
    finally:
        await scraper.shutdown()


app = FastAPI(title="JellyNama Sidecar", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class DownloadRequest(BaseModel):
    title: str
    url: str
    subdir: str = ""


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
    job_id = await downloader.enqueue(title=req.title, url=req.url, subdir=req.subdir)
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def api_status(job_id: str) -> dict:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job.to_dict()


@app.get("/api/jobs")
async def api_jobs() -> list[dict]:
    return [j.to_dict() for j in queue.list()]


if settings.plugin_dir.exists():
    app.mount("/plugin", StaticFiles(directory=str(settings.plugin_dir)), name="plugin")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.sidecar_host, port=settings.sidecar_port, reload=False)
