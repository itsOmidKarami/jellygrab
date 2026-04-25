# JellyNama — Jellyfin Plugin

A Jellyfin .NET plugin that adds a Dashboard page wired to the [JellyNama sidecar](../sidecar/) for searching 30nama.com and queuing downloads into your library.

## Architecture

```
[JF Dashboard page] ── HTTP ──▶ [Sidecar :8765] ── Playwright ──▶ 30nama.com
        ▲                              │
        │                              └── httpx stream ──▶ /media/downloads/*.mkv
        └────────── REST ─────────── [Jellyfin :8096] ── library refresh
```

The plugin is a thin shell: a single Dashboard page (HTML+JS embedded as resources in the DLL) that calls the sidecar API. All heavy lifting — scraping, downloading, JF library check/refresh — lives in the Python sidecar.

## Build

Requires the .NET 8 SDK.

```bash
cd jellyfin-plugin
dotnet publish -c Release
```

The DLL lands at `bin/Release/net8.0/publish/Jellyfin.Plugin.JellyNama.dll`.

## Install (manual / dev)

1. Find your Jellyfin plugins directory:
   - Docker: `/config/plugins/`
   - Linux: `/var/lib/jellyfin/plugins/` or `~/.local/share/jellyfin/plugins/`
   - macOS: `~/Library/Application Support/jellyfin/plugins/`
2. Create a folder `JellyNama_0.1.0.0/` and drop the published DLL inside.
3. Restart Jellyfin.
4. Dashboard → Plugins → My Plugins → JellyNama → set the Sidecar URL.

## Install (via plugin repository)

1. Build the plugin, zip the publish output: `zip JellyNama_0.1.0.0.zip Jellyfin.Plugin.JellyNama.dll`.
2. Compute MD5: `md5sum JellyNama_0.1.0.0.zip` and update `manifest.json`'s `checksum` and `sourceUrl`.
3. Host the zip + manifest.json somewhere reachable.
4. In Jellyfin Dashboard → Plugins → Repositories → Add, point at the manifest URL.
5. Catalog → JellyNama → Install.

## Usage

After install, "JellyNama" appears in the Dashboard sidebar. The page has:
- **Sidecar URL** field — set to where the sidecar is reachable from your browser (default `http://localhost:8765`).
- **Search** box — queries 30nama via the sidecar.
- **Result cards** — show "In library" badge if Jellyfin already has the title.
- **Load options** → quality buttons → click to enqueue a download.
- **Downloads** panel — live progress, polled every 2s.

## Notes

- The sidecar must be running and reachable from the browser (not just from the JF server).
- Sidecar already serves CORS `*`, so cross-origin from JF works.
- Plugin GUID: `3a8d4f2e-7c1b-4e6a-9f8d-2b5e1a9c4d7e`.
