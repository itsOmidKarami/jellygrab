# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What This Is

JellyNama is a Jellyfin companion that searches 30nama.com (Persian media site), downloads `.mkv`/`.mp4` files via direct HTTP, and triggers a Jellyfin library refresh. It has two parts:

- **`sidecar/`** — Python 3.12 + FastAPI backend (the brains)
- **`jellyfin-plugin/`** — JS frontend plugin loaded by Jellyfin's web client

Both are deployed via `docker-compose.yml` on the same Docker network as Jellyfin.

## Source of Truth

The implementation plan lives in [docs/plan.md](docs/plan.md). Phases are sequential: don't start Phase 2 work before Phase 1 is functional.

## Conventions

- **Python:** async/await throughout (FastAPI + `httpx`). No `requests`, no sync I/O in route handlers.
- **No auth.** The sidecar runs on a private Docker network. Don't add API keys or login flows unless the user asks.
- **Config via env vars only.** `JELLYFIN_URL`, `JELLYFIN_API_KEY`, `DOWNLOAD_DIR`. Read them in `sidecar/config.py`.
- **Job state is in-memory.** A simple `dict[str, JobStatus]` in `queue.py`. No Redis, no DB — kept intentionally simple.
- **JS plugin is vanilla.** No build step, no React, no TypeScript. Just `.js` and `.html` files served statically by the sidecar.

## Working With 30nama.com

The site structure must be inspected before writing the scraper — don't guess selectors. When implementing `scraper.py`, fetch a real page first and verify the HTML shape. The site exposes direct `.mkv`/`.mp4` links on detail pages (no torrents, no JS rendering required as far as we know).

## Jellyfin API Notes

- Library search: `GET /Items?searchTerm=<title>` with header `X-Emby-Token: <api_key>`
- Refresh: `POST /Library/Refresh` with the same header
- The sidecar reaches Jellyfin via its Docker service name (e.g. `http://jellyfin:8096`)

## Don't

- Don't add a database, Celery, or Redis. The job queue is in-memory by design.
- Don't propose a C#/.NET native plugin — the user explicitly chose the sidecar route.
- Don't add authentication unless asked.
- Don't introduce a frontend framework for the JS plugin.
