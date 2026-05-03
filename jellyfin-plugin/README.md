# JellyGrab — Jellyfin Plugin

The Jellyfin .NET plugin half of [JellyGrab](../README.md). Adds a Dashboard
page wired to the JellyGrab FastAPI sidecar, plus a small JS injection that
puts a "Search the web" button into Jellyfin's built-in search view.

## Install (manual)

1. Build the plugin (see "Build" below) or download a release zip.
2. Create a folder named for the plugin assembly version, for example
   `JellyGrab_0.2.3.0/`, under your Jellyfin
   `config/plugins/` directory and drop the published DLL inside.
3. Restart Jellyfin.
4. Dashboard → Plugins → My Plugins → JellyGrab → set the Sidecar URL.

## Install (via plugin catalog) — recommended

The manifest is already hosted on GitHub and kept up to date by CI.

1. In Jellyfin: Dashboard → Plugins → Repositories → add this URL:

   ```text
   https://raw.githubusercontent.com/itsOmidKarami/jellygrab/main/jellyfin-plugin/manifest.json
   ```

2. Dashboard → Plugins → Catalog → JellyGrab → Install.
3. Restart Jellyfin when prompted.
4. Dashboard → Plugins → My Plugins → JellyGrab → set the Sidecar URL.

## What It Does

After install, "JellyGrab" appears in the Dashboard sidebar. The page lets
you search any active scraper, see results, and queue downloads.

## Build

`dotnet publish jellyfin-plugin/Jellyfin.Plugin.JellyGrab.csproj -c Release -o publish`

To target a different Jellyfin minor version, pass
`-p:JellyfinVersion=10.11.0` (or whichever).
