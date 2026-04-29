# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What This Is

JellyGrab is a Jellyfin downloader companion: a FastAPI sidecar plus a Jellyfin plugin. Scrapers are pluggable under `sidecar/scrapers/<name>/`. One reference scraper (`sidecar/scrapers/nama/`) targets 30nama.com (a Persian-language media site).

- **`sidecar/`** — Python 3.12 + FastAPI backend (the brains)
- **`jellyfin-plugin/`** — .NET 9 Jellyfin plugin (`Jellyfin.Plugin.JellyGrab.dll`) that embeds vanilla JS/HTML as resources, serves them via `JellyGrabController`, and patches Jellyfin web's `index.html` (`InjectScriptService`) to load `inject.js` into every page

Sidecar is deployed via `docker-compose.yml` on the same Docker network as Jellyfin. The plugin is installed into Jellyfin as a normal Jellyfin plugin (DLL drop or via the manifest in `jellyfin-plugin/manifest.json`).

## Conventions

- **Python:** async/await throughout (FastAPI + `httpx`). No `requests`, no sync I/O in route handlers.
- **No auth.** The sidecar runs on a private Docker network. Don't add API keys or login flows unless the user asks.
- **Config via env vars only.** `JELLYFIN_URL`, `JELLYFIN_API_KEY`, `DOWNLOAD_DIR`. Read them in `sidecar/config.py`.
- **Job state is in-memory.** A simple `dict[str, JobStatus]` in `job_queue.py`. No Redis, no DB — kept intentionally simple.
- **Plugin frontend is vanilla JS.** No React, no TypeScript, no JS bundler. The `.js` / `.html` files in `jellyfin-plugin/Web/` are embedded into the DLL at build time (see the `EmbeddedResource` items in `Jellyfin.Plugin.JellyGrab.csproj`) and served by `JellyGrabController`. The .NET build itself (`dotnet publish`) is the only build step.

## Working With 30nama.com

The 30nama scraper lives in `sidecar/scrapers/nama/`. The site structure must be inspected before changing selectors — don't guess. The site exposes direct `.mkv`/`.mp4` links on detail pages (no torrents, no JS rendering required as far as we know). Login is captcha-gated, so the scraper relies on browser-exported cookies (`NAMA_COOKIE` / `NAMA_COOKIES_FILE`).

## Jellyfin API Notes

- Library search: `GET /Items?searchTerm=<title>` with header `X-Emby-Token: <api_key>`
- Refresh: `POST /Library/Refresh` with the same header
- The sidecar reaches Jellyfin via its Docker service name (e.g. `http://jellyfin:8096`)

## Don't

- Don't add a database, Celery, or Redis. The job queue is in-memory by design.
- Don't move heavy logic (scraping, downloading, job state) into the .NET plugin. The plugin is a thin shell — UI + a tiny controller for serving embedded JS and proxying to the sidecar. The Python sidecar is the brains.
- Don't add authentication unless asked.
- Don't introduce a frontend framework or JS bundler for the plugin UI.
- Don't reframe the project away from "generic downloader framework with one example scraper". The narrative is intentional.
