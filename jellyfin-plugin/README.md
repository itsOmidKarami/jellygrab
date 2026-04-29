# JellyGrab — Jellyfin Plugin

The Jellyfin .NET plugin half of [JellyGrab](../README.md). Adds a Dashboard
page wired to the JellyGrab FastAPI sidecar, plus a small JS injection that
puts a "Search the web" button into Jellyfin's built-in search view.

## Install (manual)

1. Build the plugin (see "Build" below) or download a release zip.
2. Create a folder `JellyGrab_0.1.0.0/` under your Jellyfin
   `config/plugins/` directory and drop the published DLL inside.
3. Restart Jellyfin.
4. Dashboard → Plugins → My Plugins → JellyGrab → set the Sidecar URL.

## Install (via plugin catalog)

1. Build the plugin and zip the publish output:
   `zip JellyGrab_0.1.0.0.zip Jellyfin.Plugin.JellyGrab.dll`
2. Compute MD5: `md5sum JellyGrab_0.1.0.0.zip` and update `manifest.json`'s
   `checksum` and `sourceUrl`.
3. Host the zip and updated `manifest.json` somewhere reachable.
4. In Jellyfin: Dashboard → Plugins → Repositories → add the manifest URL.
5. Catalog → JellyGrab → Install.

## What It Does

After install, "JellyGrab" appears in the Dashboard sidebar. The page lets
you search any active scraper, see results, and queue downloads.

## Build

`dotnet publish jellyfin-plugin/Jellyfin.Plugin.JellyGrab.csproj -c Release -o publish`

To target a different Jellyfin minor version, pass
`-p:JellyfinVersion=10.11.0` (or whichever).
