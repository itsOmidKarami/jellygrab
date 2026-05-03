#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: $0 <jellyfin-version> <target-framework> <version> <output-dir>" >&2
  exit 2
fi

JELLYFIN_VERSION="$1"
TARGET_FRAMEWORK="$2"
VERSION="$3"
OUTPUT_DIR="$4"

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PLUGIN_PROJECT="$REPO_ROOT/jellyfin-plugin/Jellyfin.Plugin.JellyGrab.csproj"
PUBLISH_DIR="$REPO_ROOT/jellyfin-plugin/publish-$JELLYFIN_VERSION"
OUTPUT_DIR_ABS=$(mkdir -p "$OUTPUT_DIR" && cd "$OUTPUT_DIR" && pwd)
ZIP_NAME="jellygrab-jellyfin-$JELLYFIN_VERSION.zip"
ASSEMBLY_VERSION="$VERSION.0"

rm -rf "$PUBLISH_DIR"
rm -f "$OUTPUT_DIR_ABS/$ZIP_NAME"

dotnet restore "$PLUGIN_PROJECT" \
  -p:JellyfinVersion="$JELLYFIN_VERSION" \
  -p:TargetFramework="$TARGET_FRAMEWORK"

dotnet build "$PLUGIN_PROJECT" -c Release --no-restore \
  -p:JellyfinVersion="$JELLYFIN_VERSION" \
  -p:TargetFramework="$TARGET_FRAMEWORK" \
  -p:Version="$VERSION" \
  -p:AssemblyVersion="$ASSEMBLY_VERSION" \
  -p:FileVersion="$ASSEMBLY_VERSION" \
  -p:ContinuousIntegrationBuild=true \
  -p:Deterministic=true

dotnet publish "$PLUGIN_PROJECT" -c Release --no-build \
  -p:JellyfinVersion="$JELLYFIN_VERSION" \
  -p:TargetFramework="$TARGET_FRAMEWORK" \
  -p:Version="$VERSION" \
  -p:AssemblyVersion="$ASSEMBLY_VERSION" \
  -p:FileVersion="$ASSEMBLY_VERSION" \
  -p:ContinuousIntegrationBuild=true \
  -p:Deterministic=true \
  -o "$PUBLISH_DIR"

test -f "$PUBLISH_DIR/Jellyfin.Plugin.JellyGrab.dll"

# Keep the zip metadata stable so checksums computed in the release PR match
# the assets uploaded by the tag-triggered release workflow.
touch -t 198001010000.00 "$PUBLISH_DIR/Jellyfin.Plugin.JellyGrab.dll"
(cd "$PUBLISH_DIR" && TZ=UTC zip -X -j "$OUTPUT_DIR_ABS/$ZIP_NAME" Jellyfin.Plugin.JellyGrab.dll)

echo "$OUTPUT_DIR_ABS/$ZIP_NAME"
