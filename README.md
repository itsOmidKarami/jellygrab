# JellyGrab

A self-hosted Jellyfin companion that adds search-and-download for arbitrary
media sources to your Jellyfin server. JellyGrab ships as a small FastAPI
**sidecar** plus a thin **Jellyfin plugin** that surfaces a downloader page
inside Jellyfin's web UI.

Scrapers are pluggable: each scraper is a Python module under
`sidecar/scrapers/<name>/` that implements a small async interface. One
reference scraper for [30nama.com](https://30nama.com) (a Persian-language
media site) is included as an example.

## How It Works

1. The **FastAPI sidecar** runs in Docker alongside Jellyfin
2. The **Jellyfin plugin** adds a "JellyGrab" page to Jellyfin's dashboard and
   injects a search button into Jellyfin's built-in search view
3. You search → the sidecar checks your library, then asks the active scraper
   for matches
4. You click Download → the sidecar streams the file into the watched folder
5. When the download finishes, the sidecar tells Jellyfin to refresh its
   library

```text
[Jellyfin Web UI]
     │
     │ (injected JS, served by the plugin)
     ▼
[JellyGrab Plugin] ──HTTP──▶ [FastAPI Sidecar]
                                   │
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
           Scraper plugin    Jellyfin API       Media folder
           (e.g. 30nama)   (lib check + scan)   (download dest)
```

## Project Structure

```text
jellygrab/
├── sidecar/                # Python FastAPI backend
│   └── scrapers/
│       └── nama/           # Bundled 30nama.com scraper (reference impl)
├── jellyfin-plugin/        # Jellyfin .NET plugin (C#)
├── docker-compose.yml      # Runs the whole stack
└── docs/
    └── scrapers.md         # How to write your own scraper
```

## Quick Start

1. Copy `.env.example` to `.env` and fill in `JELLYFIN_URL`, `JELLYFIN_API_KEY`,
   `DOWNLOAD_DIR`, and any scraper-specific values you need
2. `docker compose up -d`
3. Install the plugin DLL into Jellyfin (see
   [jellyfin-plugin/README.md](jellyfin-plugin/README.md))
4. In Jellyfin: Dashboard → Plugins → JellyGrab → set the sidecar URL

## Included Scrapers

### 30nama (`sidecar/scrapers/nama/`)

A reference scraper for 30nama.com. Requires browser cookies (login is
captcha-gated). See `sidecar/scrapers/nama/` for details and
[.env.example](.env.example) for the `NAMA_*` configuration.

## Writing Your Own Scraper

See [docs/scrapers.md](docs/scrapers.md). Briefly: create
`sidecar/scrapers/<your_scraper>/`, expose `startup()`, `shutdown()`,
`search()`, and `get_download_options()` as async functions matching the
shape in `sidecar/scrapers/__init__.py`, and import it from `sidecar/main.py`.

## Jellyfin Compatibility

Jellyfin's plugin ABI changes between minor releases. A DLL built against
10.11 **will not load on 10.10 or 10.12** — Jellyfin checks `targetAbi` and
refuses the load. If you upgrade Jellyfin to a new minor version, you need a
JellyGrab release built against that version.

To rebuild for a different ABI, bump `Jellyfin.Controller` and `Jellyfin.Model`
versions in
[jellyfin-plugin/Jellyfin.Plugin.JellyGrab.csproj](jellyfin-plugin/Jellyfin.Plugin.JellyGrab.csproj)
(or pass `-p:JellyfinVersion=X.Y.Z` at build time).

## Plugin ↔ Sidecar Compatibility

The plugin DLL and the sidecar image are released under the same `vX.Y.Z` git
tag — that's the lockstep half. The runtime half is a version handshake:

- The sidecar exposes `GET /api/version` returning `{api, build}`.
- `inject.js` declares `EXPECTED_API_VERSION` and warns inside the search modal
  if the sidecar's `api` doesn't match.

`api` is bumped only when an `/api/*` route the plugin uses is removed or
breaking-changed. Adding new routes or new optional fields does **not** bump
it. So a plugin and sidecar from different builds usually still work — the
handshake just tells you loudly when they don't.

The sidecar's `api` version is independent of Jellyfin — the sidecar only uses
stable Jellyfin HTTP endpoints (`/Items`, `/Library/Refresh`), so a sidecar
release is **not** required for every Jellyfin upgrade. Only the plugin DLL
needs rebuilding when Jellyfin's plugin ABI changes.

## Disclaimer

JellyGrab is a generic downloader framework. It does **not** host, distribute,
or endorse any media content. The bundled 30nama scraper is provided as a
reference implementation only. **You are responsible for ensuring that your
use of this software, including any scrapers you enable or write, complies
with the laws of your jurisdiction and the terms of service of any sites you
interact with.**

The maintainers accept no liability for misuse. If you don't have the right
to download a piece of media, don't.

## License

[MIT](LICENSE)
