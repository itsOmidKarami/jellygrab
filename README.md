# JellyNama

A companion service for [Jellyfin](https://jellyfin.org/) that lets you search [30nama.com](https://30nama.com) for Persian movies and series, download them directly into your Jellyfin media folder, and trigger an automatic library refresh — all from inside Jellyfin's own web interface.

## How It Works

1. A **Python/FastAPI sidecar** runs alongside Jellyfin in Docker
2. A **Jellyfin JS plugin** adds a "JellyNama" page to Jellyfin's sidebar
3. You search → sidecar checks your library, then scrapes 30nama.com for matches
4. You click Download → sidecar streams the `.mkv`/`.mp4` to the watched folder
5. When the download finishes, the sidecar tells Jellyfin to refresh its library

```
[Jellyfin Web UI]
     │
     │ (JS plugin)
     ▼
[JellyNama Plugin] ──HTTP──▶ [FastAPI Sidecar]
                                    │
                ┌───────────────────┼────────────────┐
                ▼                   ▼                ▼
           30nama.com         Jellyfin API      Media folder
           (scraper)        (lib check + scan)  (download dest)
```

## Project Structure

```
jellynama/
├── sidecar/            # Python FastAPI backend
├── jellyfin-plugin/    # Jellyfin frontend JS plugin
├── docker-compose.yml  # Runs the whole stack
└── docs/
    └── plan.md         # Implementation plan
```

## Status

🚧 In development. See [docs/plan.md](docs/plan.md) for the implementation roadmap.

## Stack

- **Backend:** Python 3.12, FastAPI, httpx, BeautifulSoup
- **Frontend:** Jellyfin JS plugin (vanilla JS)
- **Deployment:** Docker Compose, joined to Jellyfin's Docker network
