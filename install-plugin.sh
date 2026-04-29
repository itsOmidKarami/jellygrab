#!/usr/bin/env bash
# Copies the locally-built JellyGrab plugin DLL into Jellyfin's plugins dir
# (the host-side bind-mount of /config). Run after `dotnet publish` and
# whenever you rebuild the plugin.
set -euo pipefail

cd "$(dirname "$0")"

SRC="jellyfin-plugin/bin/Release/net9.0/publish/Jellyfin.Plugin.JellyGrab.dll"
DST_DIR="jellyfin/config/plugins/JellyGrab_0.1.0"

if [[ ! -f "$SRC" ]]; then
  echo "Plugin DLL not found at $SRC" >&2
  echo "Build it first: cd jellyfin-plugin && dotnet publish -c Release" >&2
  exit 1
fi

mkdir -p "$DST_DIR"
cp "$SRC" "$DST_DIR/"
echo "Installed: $DST_DIR/Jellyfin.Plugin.JellyGrab.dll"
echo "Restart Jellyfin to pick up the change: docker compose restart jellyfin"
