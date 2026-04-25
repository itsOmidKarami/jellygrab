# JellyNama — Project Plan

## What We're Building

A companion service for Jellyfin that lets users search 30nama.com for Persian movies/series, checks whether content already exists locally, and triggers a direct HTTP download into the Jellyfin-watched folder. Accessed via a native Jellyfin JS frontend plugin (adds a sidebar menu item). Backend is a Python/FastAPI sidecar running alongside Jellyfin in Docker.

---

## Architecture

```
[Jellyfin Web UI]
     |
     | (JS plugin loaded by JF's web client)
     v
[JellyNama JS Plugin]  <--HTTP-->  [FastAPI Sidecar :8765]
                                          |
                            ┌─────────────┼──────────────┐
                            v             v              v
                      30nama.com     Jellyfin API    File system
                      (scraper)      (lib check +    (download
                                     refresh)         target dir)
```

---

## Project Structure

```
jellynama/
├── sidecar/
│   ├── main.py            # FastAPI app + routes
│   ├── scraper.py         # 30nama.com search & link extraction
│   ├── downloader.py      # Async HTTP download + progress tracking
│   ├── jellyfin_client.py # Jellyfin REST API (search library, refresh)
│   ├── queue.py           # In-memory download queue (id → status/progress)
│   ├── config.py          # Settings from env vars
│   ├── requirements.txt
│   └── Dockerfile
├── jellyfin-plugin/
│   ├── plugin.js          # Plugin manifest + registration
│   ├── jellynama.js       # Page logic (search, download, progress polling)
│   └── jellynama.html     # Page template
└── docker-compose.yml
```

---

## Phases

### Phase 1 — Python Sidecar Core
**Goal:** Working API backend with no frontend yet.

- [ ] `sidecar/config.py` — env-based settings (JF URL, API key, download dir)
- [ ] `sidecar/requirements.txt` + `sidecar/Dockerfile`
- [ ] `sidecar/scraper.py` — investigate 30nama.com structure, implement search + direct link extraction
- [ ] `sidecar/queue.py` — in-memory job store `dict[str, JobStatus]`
- [ ] `sidecar/downloader.py` — async streaming download, progress updates, triggers library refresh on completion
- [ ] `sidecar/jellyfin_client.py` — library search + refresh via Jellyfin REST API
- [ ] `sidecar/main.py` — FastAPI routes, CORS enabled, serves plugin files statically

**API surface:**
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/search?q=<title>` | Search 30nama + check JF library |
| `POST` | `/api/download` | Enqueue a download job |
| `GET` | `/api/status/{job_id}` | Poll download progress |
| `GET` | `/api/jobs` | List all jobs |

**Verification:** `curl http://localhost:8765/api/search?q=test` returns JSON results from 30nama.

---

### Phase 2 — Jellyfin JS Plugin
**Goal:** Search and download accessible from inside Jellyfin's own UI.

- [ ] `jellyfin-plugin/plugin.js` — plugin metadata, registers `/jellynama` page route in JF's router
- [ ] `jellyfin-plugin/jellynama.html` — page template with search input + results area
- [ ] `jellyfin-plugin/jellynama.js` — calls sidecar API, renders result cards, handles download + progress polling

**UI behavior:**
- Search input → `GET /api/search` → result cards (title, year, poster, quality options, "Already in library" badge)
- "Download" button → `POST /api/download` → polls `GET /api/status/{id}` every 2s → progress bar → done

**Installation:** Sidecar serves `jellyfin-plugin/` at `/plugin/*`. User adds the manifest URL in Jellyfin Dashboard → Plugins → Repositories.

---

### Phase 3 — Docker Compose & Integration
**Goal:** Everything runs together with one command.

- [ ] `docker-compose.yml` — sidecar joins Jellyfin's Docker network, shared media volume, env vars from `.env`
- [ ] `.env.example` — template for `JELLYFIN_URL`, `JELLYFIN_API_KEY`, `DOWNLOAD_DIR`
- [ ] End-to-end test: search → download → file in folder → JF library refresh → "Already in library" badge on re-search

---

## Key Decisions

| Decision | Choice | Reason |
|---|---|---|
| Backend language | Python (FastAPI) | Avoid .NET/C#, fast iteration |
| Download method | Direct HTTP streaming (`httpx`) | 30nama.com exposes direct .mkv/.mp4 URLs |
| UI integration | Jellyfin JS plugin | Native look inside JF, no separate browser tab |
| Auth | None | Private/local Docker network |
| Download tool | `httpx` async streaming | Simple, no subprocess, works for direct links |
