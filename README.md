# JellyNama

A companion service for [Jellyfin](https://jellyfin.org/) that lets you search [30nama.com](https://30nama.com) for Persian movies and series, download them directly into your Jellyfin media folder, and trigger an automatic library refresh — all from inside Jellyfin's own web interface.

## How It Works

1. A **Python/FastAPI sidecar** runs alongside Jellyfin in Docker
2. A **Jellyfin .NET plugin** adds a "JellyNama" page to Jellyfin's dashboard and injects 30nama search into the built-in search view
3. You search → sidecar checks your library, then scrapes 30nama.com for matches
4. You click Download → sidecar streams the `.mkv`/`.mp4` to the watched folder
5. When the download finishes, the sidecar tells Jellyfin to refresh its library

```text
[Jellyfin Web UI]
     │
     │ (injected JS, served by the plugin)
     ▼
[JellyNama Plugin] ──HTTP──▶ [FastAPI Sidecar]
                                    │
                ┌───────────────────┼────────────────┐
                ▼                   ▼                ▼
           30nama.com         Jellyfin API      Media folder
           (scraper)        (lib check + scan)  (download dest)
```

## Project Structure

```text
jellynama/
├── sidecar/            # Python FastAPI backend
├── jellyfin-plugin/    # Jellyfin .NET plugin (C#)
├── docker-compose.yml  # Runs the whole stack
└── docs/
    └── plan.md         # Implementation plan
```

## Status

🚧 In development. See [docs/plan.md](docs/plan.md) for the implementation roadmap.

## Stack

- **Backend:** Python 3.12, FastAPI, httpx, BeautifulSoup
- **Plugin:** C# / .NET 9, built against the Jellyfin plugin SDK
- **Deployment:** Docker Compose, joined to Jellyfin's Docker network

## Jellyfin Compatibility

| JellyNama | Jellyfin | .NET | targetAbi |
|-----------|----------|------|-----------|
| 0.1.x     | 10.11.x  | 9.0  | 10.11.0.0 |

Jellyfin's plugin ABI changes between minor releases. A DLL built against 10.11 **will not load on 10.10 or 10.12** — Jellyfin checks `targetAbi` and refuses the load. If you upgrade Jellyfin to a new minor version, you need a JellyNama release built against that version.

The `docker-compose.yml` in this repo pins `jellyfin/jellyfin:10.11.8` to keep the runtime aligned with the plugin. If you want to upgrade Jellyfin, also bump:

- `Jellyfin.Controller` and `Jellyfin.Model` versions in [jellyfin-plugin/Jellyfin.Plugin.JellyNama.csproj](jellyfin-plugin/Jellyfin.Plugin.JellyNama.csproj) (or pass `-p:JellyfinVersion=X.Y.Z` at build time)
- `targetAbi` in [jellyfin-plugin/build.yaml](jellyfin-plugin/build.yaml) and [jellyfin-plugin/manifest.json](jellyfin-plugin/manifest.json)
- The `jellyfin/jellyfin` image tag in [docker-compose.yml](docker-compose.yml)

CI builds the plugin against every supported Jellyfin version (see [.github/workflows/build-plugin.yml](.github/workflows/build-plugin.yml)) — add a new entry to the matrix when supporting a new minor.

## Download Layout

The sidecar routes downloads by content type so Jellyfin's library matcher gets clean folder paths:

| Content kind | Default destination | Override env var |
|--------------|---------------------|------------------|
| Movie        | `/media/Movies`     | `MOVIES_DIR`     |
| Series       | `/media/TV Shows`   | `TV_DIR`         |
| Unknown      | `/media/downloads`  | `DOWNLOAD_DIR`   |

Each item gets its own folder, so a downloaded movie ends up at `/media/Movies/Title (Year)/Title (Year).mkv` — the layout Jellyfin's matcher expects. Point your Jellyfin Movies library at `MOVIES_DIR` and your TV library at `TV_DIR`. The "unknown" path is a fallback for hits 30nama doesn't classify; pointing a library at it is not recommended.

> **Migrating from the old flat layout:** earlier versions dumped everything into `/media/downloads`. If you've been using that, move existing files into the new per-item folders by hand (or just leave them — the old library will keep working) before pointing your Movies/TV libraries at the new roots.

## Building the Plugin

```bash
cd jellyfin-plugin
dotnet publish -c Release
../install-plugin.sh           # copies the DLL into jellyfin/config/plugins/
docker compose restart jellyfin
```

To target a different Jellyfin version:

```bash
dotnet publish -c Release -p:JellyfinVersion=10.11.9
```
