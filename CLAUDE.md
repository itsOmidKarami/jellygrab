# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What This Is

JellyGrab is a Jellyfin downloader companion: a FastAPI sidecar plus a Jellyfin plugin. Scrapers are pluggable under `sidecar/scrapers/<name>/`. One reference scraper (`sidecar/scrapers/nama/`) targets 30nama.com (a Persian-language media site).

- **`sidecar/`** — Python 3.12 + FastAPI backend (the brains)
- **`jellyfin-plugin/`** — JS frontend plugin loaded by Jellyfin's web client

Both are deployed via `docker-compose.yml` on the same Docker network as Jellyfin.

## Conventions

- **Python:** async/await throughout (FastAPI + `httpx`). No `requests`, no sync I/O in route handlers.
- **No auth.** The sidecar runs on a private Docker network. Don't add API keys or login flows unless the user asks.
- **Config via env vars only.** `JELLYFIN_URL`, `JELLYFIN_API_KEY`, `DOWNLOAD_DIR`. Read them in `sidecar/config.py`.
- **Job state is in-memory.** A simple `dict[str, JobStatus]` in `job_queue.py`. No Redis, no DB — kept intentionally simple.
- **JS plugin is vanilla.** No build step, no React, no TypeScript. Just `.js` and `.html` files served statically by the sidecar.

## Working With 30nama.com

The 30nama scraper lives in `sidecar/scrapers/nama/`. The site structure must be inspected before changing selectors — don't guess. The site exposes direct `.mkv`/`.mp4` links on detail pages (no torrents, no JS rendering required as far as we know). Login is captcha-gated, so the scraper relies on browser-exported cookies (`NAMA_COOKIE` / `NAMA_COOKIES_FILE`).

## Jellyfin API Notes

- Library search: `GET /Items?searchTerm=<title>` with header `X-Emby-Token: <api_key>`
- Refresh: `POST /Library/Refresh` with the same header
- The sidecar reaches Jellyfin via its Docker service name (e.g. `http://jellyfin:8096`)

## Don't

- Don't add a database, Celery, or Redis. The job queue is in-memory by design.
- Don't propose a C#/.NET native plugin — the user explicitly chose the sidecar route.
- Don't add authentication unless asked.
- Don't introduce a frontend framework for the JS plugin.
- Don't reframe the project away from "generic downloader framework with one example scraper". The narrative is intentional — see `docs/superpowers/specs/2026-04-29-public-release-design.md`.
