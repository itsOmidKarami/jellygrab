# Building a Custom Jellyfin Plugin: External Library Search & Download

## Overview

Jellyfin supports a first-class **plugin system** built on **.NET** (targeting `net8.0`), making it entirely possible to add external library search, download triggering, and automatic library refresh functionality[1]. The official plugin template is available at `jellyfin/jellyfin-plugin-template` on GitHub[1][2]. A working real-world reference for this pattern is **FinTube** (`AECX/FinTube`), a Jellyfin plugin that imports media directly from YouTube via `yt-dlp`[3].

***

## How It Works: The Full Workflow

The desired feature maps cleanly onto Jellyfin's plugin model in the following steps:

1. **User searches** → A custom `ControllerBase` REST endpoint (inside the plugin) handles the request
2. **Check local library** → `ILibraryManager` queries whether the item already exists in Jellyfin
3. **Cache miss → External search** → An `HttpClient` call inside the plugin queries the external website
4. **Return results** → Served back to the Jellyfin frontend (or a companion web UI)
5. **User clicks Download** → Plugin triggers a download (via `yt-dlp`, `aria2`, or direct `HttpClient`) into the watched library folder
6. **Trigger library refresh** → A `POST /Library/Refresh` API call with the Jellyfin API key picks up the new file[4]
7. **Play** → The item is available in Jellyfin immediately after the scan completes

***

## Plugin Architecture

### Language & Framework

| Property | Value |
|---|---|
| Language | C# (primary), F# or VB.NET also work |
| Target Framework | `net8.0` |
| Template | `jellyfin/jellyfin-plugin-template` (GitHub)[1] |
| Plugin type | Server-side DLL loaded by Jellyfin at startup |

### Core Interfaces

| Interface | Purpose | Use in This Plugin |
|---|---|---|
| `ILibraryManager` | Query and manage local media items | Check if requested item already exists locally |
| `ControllerBase` | Expose custom HTTP/REST endpoints (ASP.NET) | Search API + download trigger endpoint |
| `IScheduledTask` | Background async task runner[5] | Download queue worker running independently |
| `ILibraryPostScanTask` | Hook that fires after a library scan | React to newly added files post-download |
| `IItemResolver` | Define custom media type resolution | Optional — for exotic or non-standard media types |

***

## Implementation Details

### 1. Local Library Check

```csharp
var results = _libraryManager.GetItemList(new InternalItemsQuery
{
    Name = searchTitle,
    IncludeItemTypes = new[] { BaseItemKind.Movie, BaseItemKind.Series }
});

if (results.Count > 0)
    return AlreadyExistsResponse(results.First());
```

### 2. Custom REST Endpoint

Extend `ControllerBase` to expose endpoints Jellyfin's frontend (or your own web UI) can call:

```csharp
[ApiController]
[Route("ExternalSearch")]
public class ExternalSearchController : ControllerBase
{
    [HttpGet("Search")]
    public async Task<IActionResult> Search([FromQuery] string title)
    {
        // 1. Check local library
        // 2. If miss → call external site
        // 3. Return results
    }

    [HttpPost("Download")]
    public async Task<IActionResult> TriggerDownload([FromBody] DownloadRequest request)
    {
        // Enqueue download job
    }
}
```

### 3. Triggering a Library Refresh

After the file lands in the watched folder, a single API call refreshes the library[4]:

```bash
curl -X POST 'http://localhost:8096/Library/Refresh' \
  -H 'X-Emby-Token: YOUR_API_KEY'
```

Or from within the plugin using `ILibraryManager.ValidateMediaLibrary()`.

### 4. Download Backend Options

| Tool | Method | Best For |
|---|---|---|
| `yt-dlp` | Shell process via `Process.Start()` | Video sites, streaming |
| `aria2` | HTTP via `aria2c --enable-rpc` | Direct HTTP/FTP, multi-connection |
| `HttpClient` | Native .NET | Simple direct file downloads |

FinTube uses `yt-dlp` called as a subprocess — this is the proven pattern[3].

***

## Alternative: Python Sidecar Service

If avoiding .NET/C# is preferable, a lightweight **sidecar microservice** achieves the same result:

- Write the external search + download logic in **Python** (using `requests`, `yt-dlp`, etc.)
- Use the **Jellyfin REST API** from Python to check the local library and trigger refreshes
- Add the official **Jellyfin Webhook plugin** to wire Jellyfin events to the sidecar[6]
- Expose a simple web UI (Flask/FastAPI) that complements the Jellyfin interface

This approach trades the tight JF integration of a native plugin for much faster iteration speed in Python.

**Trade-off summary:**

| Approach | Pros | Cons |
|---|---|---|
| Native C# Plugin | Deep JF integration, lives inside JF | Requires .NET build pipeline, C# |
| Python Sidecar | Fast iteration, familiar language | Separate process, slightly looser integration |

***

## Getting Started

### Step 1 — Clone the Plugin Template

```bash
git clone https://github.com/jellyfin/jellyfin-plugin-template.git
cd jellyfin-plugin-template
```

### Step 2 — Study FinTube as Reference

`github.com/AECX/FinTube` is the closest working reference[3]. It demonstrates:
- Subprocess calls to `yt-dlp`
- File placement into the JF-watched directory
- Triggering a library refresh afterward

### Step 3 — Build & Install

```bash
dotnet build --configuration Release
# Copy the output DLL into Jellyfin's plugin directory:
# Linux: ~/.local/share/jellyfin/plugins/
# Docker: /config/plugins/
```

Restart Jellyfin to load the plugin.

### Step 4 — Trigger Library Scan via API

```bash
# Scan a specific library folder
curl -X POST "http://localhost:8096/Library/Refresh" \
  -H "X-Emby-Token: <your-api-key>"
```

***

## Key Resources

- **Plugin template**: `github.com/jellyfin/jellyfin-plugin-template`[1]
- **FinTube (reference plugin)**: `github.com/AECX/FinTube`[3]
- **Jellyfin plugin catalog**: `awesome-jellyfin/awesome-jellyfin`[6]
- **Official plugin docs**: `jellyfin.org/docs/general/server/plugins/`[7]
- **Jellyfin REST API reference**: `jellyfin.org` OpenAPI spec