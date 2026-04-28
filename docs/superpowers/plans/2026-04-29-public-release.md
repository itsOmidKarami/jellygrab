# Public Release Implementation Plan — JellyNama → JellyGrab

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the project to JellyGrab, reorganize the 30nama scraper as one example under a thin `Scraper` protocol, rewrite the README to lead with a generic-framework framing, and prepare the repo for a public GitHub release.

**Architecture:** No business logic changes. Identifier replacement (`JellyNama` → `JellyGrab`, `jellynama` → `jellygrab`), file moves into `sidecar/scrapers/nama/`, a small `Scraper` protocol stub, and documentation rewrites. The runtime behavior of the system is identical before and after.

**Tech Stack:** Python 3.12, FastAPI, .NET 8 (Jellyfin plugin), Docker Compose, GitHub Actions.

**Note on testing:** This codebase has no existing test suite — it's manually verified via `docker compose up` + a smoke flow. Adding pytest infrastructure for a rename is out of scope (YAGNI). Tasks below use a docker-based smoke test as the verification step in place of unit tests.

**Reference spec:** [docs/superpowers/specs/2026-04-29-public-release-design.md](../specs/2026-04-29-public-release-design.md)

---

## Identifier Rename Reference

Use this table consistently across all tasks. **30nama-scoped identifiers (containing `nama` to refer to *that scraper specifically*) are intentionally preserved.**

| Before                       | After                       | Notes |
|------------------------------|-----------------------------|-------|
| `JellyNama`                  | `JellyGrab`                 | display name, C# class prefix |
| `jellynama`                  | `jellygrab`                 | repo, docker, package, owner |
| `JELLYNAMA_API`              | `JELLYGRAB_API`             | injected JS global |
| `Jellyfin.Plugin.JellyNama`  | `Jellyfin.Plugin.JellyGrab` | C# namespace |
| `JellyNamaController`        | `JellyGrabController`       | C# class + `[Route("JellyGrab")]` |
| `JellyNamaJs`                | `JellyGrabJs`               | plugin page name |
| `JellyNamaConfigPage`        | `JellyGrabConfigPage`       | HTML id |
| `JellyNamaInject`            | `JellyGrabInject`           | HTML marker comment |
| `data-jellynama-injected`    | `data-jellygrab-injected`   | DOM marker attr |
| `jellynama-modal`            | `jellygrab-modal`           | DOM id |
| `jellynama-banner`           | `jellygrab-banner`          | CSS class |
| `jellynama.html`             | `jellygrab.html`            | embedded resource |
| `jellynama.js`               | `jellygrab.js`              | embedded resource |
| `JellyNama_0.1.0`            | `JellyGrab_0.1.0`           | plugin install dir |
| `Jellyfin.Plugin.JellyNama.dll` | `Jellyfin.Plugin.JellyGrab.dll` | DLL artifact |
| logger `"jellynama.*"`       | `"jellygrab.*"`             | Python loggers |
| FastAPI title `"JellyNama Sidecar"` | `"JellyGrab Sidecar"` | OpenAPI |

**Preserved (do NOT rename):**

- `nama_session.py`, `nama_base_url`, `nama_cookie`, `nama_cookies_file`, `nama_user_agent`, `NAMA_*` env vars, `NamaScraper` (and similar 30nama-scoped Python identifiers) — these correctly identify the 30nama scraper.
- `flaresolverr_session=os.getenv("FLARESOLVERR_SESSION", "jellynama")` — this is a default *session name* sent to FlareSolverr; rename the default to `"jellygrab"` since it's a project-level identifier, not 30nama-scoped.
- `JELLYFIN_URL`, `JELLYFIN_API_KEY`, `DOWNLOAD_DIR`, etc. — unchanged.

---

## Task 1: Pre-flight audit

Verify no secrets are in git history and that `.gitignore` is correct before any rename work.

**Files:**
- Read-only: `.gitignore`, full git history

- [ ] **Step 1: Audit git history for sensitive files ever committed**

Run:
```bash
git log --all --diff-filter=A --name-only --pretty=format: | sort -u | grep -iE "\.env|cookies|secret|credential|token|api.?key|\.pem|\.key" | grep -v ".env.example"
```

Expected: empty output (only `.env.example` was ever committed, and it's filtered out). If any other file appears, STOP — the user must rotate the secret and decide whether to rewrite history before publishing.

- [ ] **Step 2: Audit current working tree for accidentally tracked secrets**

Run:
```bash
git ls-files | grep -iE "\.env$|cookies|secret|credential|token|\.pem$|\.key$" | grep -v ".env.example"
```

Expected: empty output.

- [ ] **Step 3: Verify `.gitignore` covers all sensitive paths**

Confirm `.gitignore` contains: `.env`, `secrets/`, `media/`, `jellyfin/config/`, `jellyfin/cache/`, `*_cookies.json`. The current `.gitignore` already does — no change needed.

- [ ] **Step 4: Scan committed source for personal data**

Run:
```bash
git grep -nE "/Users/|/home/[a-z]+/|192\.168\.|10\.0\.|itsomidkarami|omidkarami" -- ':!docs/superpowers/' ':!CLAUDE.md'
```

Expected: empty output. (CLAUDE.md is excluded — it's intentionally personal and untracked from this perspective; will be updated in Task 11.) If anything else appears, replace it with a placeholder before proceeding.

- [ ] **Step 5: No commit for this task** — read-only audit. If issues were found, stop and resolve them before continuing.

---

## Task 2: Add LICENSE file

Add an MIT license. This is the lowest-friction OSS license and matches typical Jellyfin plugin community practice.

**Files:**
- Create: `LICENSE`

- [ ] **Step 1: Create `LICENSE` with MIT text**

Create `/Users/omidkarami/Projects/jellynama/LICENSE`:

```
MIT License

Copyright (c) 2026 Omid Karami

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Commit**

```bash
git add LICENSE
git commit -m "Add MIT license"
```

---

## Task 3: Reorganize 30nama scraper into `sidecar/scrapers/nama/` and add `Scraper` protocol stub

Move the 30nama-specific files under a `scrapers/nama/` package and add a thin `Scraper` protocol so the directory layout matches the framework framing. **Do not change behavior** — this is moves + import path updates + a new protocol file.

**Files:**
- Create: `sidecar/scrapers/__init__.py`
- Create: `sidecar/scrapers/nama/__init__.py`
- Move: `sidecar/scraper.py` → `sidecar/scrapers/nama/scraper.py`
- Move: `sidecar/nama_session.py` → `sidecar/scrapers/nama/session.py`
- Move: `sidecar/flaresolverr_client.py` → `sidecar/scrapers/nama/flaresolverr.py`
- Modify: `sidecar/main.py` (import path)
- Modify: `sidecar/keepalive.py` (import path)
- Modify: `sidecar/downloader.py` (import path, if it imports scraper)
- Modify: any other sidecar file importing the moved modules

- [ ] **Step 1: Identify all imports of the moved modules**

Run:
```bash
cd /Users/omidkarami/Projects/jellynama
grep -rn "^import scraper\|^from scraper\|^import nama_session\|^from nama_session\|^import flaresolverr_client\|^from flaresolverr_client" sidecar/
```

Note every file and import line that needs updating in steps below. Expected hits include `main.py`, `keepalive.py`, possibly `downloader.py`, and cross-imports inside the moved files themselves.

- [ ] **Step 2: Move the three files using `git mv`**

Run:
```bash
cd /Users/omidkarami/Projects/jellynama
mkdir -p sidecar/scrapers/nama
git mv sidecar/scraper.py sidecar/scrapers/nama/scraper.py
git mv sidecar/nama_session.py sidecar/scrapers/nama/session.py
git mv sidecar/flaresolverr_client.py sidecar/scrapers/nama/flaresolverr.py
```

- [ ] **Step 3: Create `sidecar/scrapers/__init__.py` with the `Scraper` protocol stub**

Create `/Users/omidkarami/Projects/jellynama/sidecar/scrapers/__init__.py`:

```python
"""Scraper plugin point.

A scraper is a module that exposes async functions for searching a media
source and resolving download options. The bundled `nama` scraper (for
30nama.com) is the reference implementation. Additional scrapers can be
added under `sidecar/scrapers/<name>/` following the same shape.
"""

from typing import Any, Protocol


class Scraper(Protocol):
    """Shape every scraper module is expected to expose.

    The protocol is structural — a scraper just needs callables with these
    names. See `scrapers/nama/scraper.py` for the reference implementation.
    """

    async def startup(self) -> None: ...

    async def shutdown(self) -> None: ...

    async def search(self, query: str) -> list[Any]: ...

    async def get_download_options(self, detail_url: str) -> list[Any]: ...
```

- [ ] **Step 4: Create `sidecar/scrapers/nama/__init__.py` re-exporting the public surface**

Create `/Users/omidkarami/Projects/jellynama/sidecar/scrapers/nama/__init__.py`:

```python
"""30nama.com scraper — reference scraper bundled with JellyGrab."""

from .scraper import (
    get_download_options,
    reseed_cookies,
    search,
    shutdown,
    startup,
    _cookie_jar,
)

__all__ = [
    "get_download_options",
    "reseed_cookies",
    "search",
    "shutdown",
    "startup",
    "_cookie_jar",
]
```

- [ ] **Step 5: Update intra-package imports inside the moved files**

In `sidecar/scrapers/nama/scraper.py`: any `import nama_session` → `from . import session as nama_session`. Any `import flaresolverr_client` → `from . import flaresolverr as flaresolverr_client`. Use the aliases so the rest of the file body doesn't have to change.

In `sidecar/scrapers/nama/session.py`: any `import flaresolverr_client` → `from . import flaresolverr as flaresolverr_client`.

Run:
```bash
cd /Users/omidkarami/Projects/jellynama
grep -n "nama_session\|flaresolverr_client" sidecar/scrapers/nama/scraper.py sidecar/scrapers/nama/session.py sidecar/scrapers/nama/flaresolverr.py
```

Verify only import lines remain to be updated (the body references via aliases stay untouched).

- [ ] **Step 6: Update top-level imports in `sidecar/main.py`**

In [sidecar/main.py](sidecar/main.py), replace:

```python
import scraper
```

with:

```python
from scrapers import nama as scraper
```

This keeps every existing `scraper.search(...)`, `scraper.startup()`, etc. call site working unchanged.

- [ ] **Step 7: Update imports in `sidecar/keepalive.py` and `sidecar/downloader.py`**

For each file in `sidecar/keepalive.py` and `sidecar/downloader.py` that imported `scraper`, `nama_session`, or `flaresolverr_client`, switch to:

```python
from scrapers import nama as scraper          # if it imported scraper
from scrapers.nama import session as nama_session  # if it imported nama_session
from scrapers.nama import flaresolverr as flaresolverr_client  # if it imported flaresolverr_client
```

Run after editing:
```bash
cd /Users/omidkarami/Projects/jellynama
grep -rn "^import scraper\|^from scraper\|^import nama_session\|^from nama_session\|^import flaresolverr_client\|^from flaresolverr_client" sidecar/
```

Expected: empty output (all old import paths replaced).

- [ ] **Step 8: Static check — Python imports resolve**

Run:
```bash
cd /Users/omidkarami/Projects/jellynama/sidecar
python3 -c "import main; print('ok')"
```

Expected: `ok`. If you see `ModuleNotFoundError` or `ImportError`, fix the offending import path before continuing. (You may need `JELLYFIN_API_KEY=test` etc. set if `load_settings()` complains — it doesn't currently, but if it does, set placeholder env vars.)

- [ ] **Step 9: Commit**

```bash
git add sidecar/
git commit -m "Reorganize 30nama scraper under scrapers/nama/ with Scraper protocol stub"
```

---

## Task 4: Rename project identifiers in Python sidecar code

Replace project-level `jellynama` / `JellyNama` strings in Python source. Preserve 30nama-scoped identifiers per the rename reference.

**Files:**
- Modify: `sidecar/main.py`
- Modify: `sidecar/config.py`
- Modify: `sidecar/scrapers/nama/scraper.py`
- Modify: `sidecar/scrapers/nama/flaresolverr.py`
- Modify: `sidecar/scrapers/nama/session.py`
- Modify: `sidecar/keepalive.py`

- [ ] **Step 1: Replace FastAPI title in `sidecar/main.py`**

In [sidecar/main.py:44](sidecar/main.py#L44):

Change `app = FastAPI(title="JellyNama Sidecar", version="0.1.0", lifespan=lifespan)` to `app = FastAPI(title="JellyGrab Sidecar", version="0.1.0", lifespan=lifespan)`.

- [ ] **Step 2: Replace logger names**

In each file, change `logging.getLogger("jellynama.<x>")` to `logging.getLogger("jellygrab.<x>")`. Affected files (preserve the suffix after the dot):

- `sidecar/scrapers/nama/scraper.py`: `"jellynama.scraper"` → `"jellygrab.scraper"`
- `sidecar/scrapers/nama/flaresolverr.py`: `"jellynama.flaresolverr"` → `"jellygrab.flaresolverr"`
- `sidecar/scrapers/nama/session.py`: `"jellynama.nama_session"` → `"jellygrab.nama_session"`
- `sidecar/keepalive.py`: `"jellynama.keepalive"` → `"jellygrab.keepalive"`

- [ ] **Step 3: Replace debug dir path**

In `sidecar/scrapers/nama/scraper.py` (around the line that was `scraper.py:301`), change:

```python
_DEBUG_DIR = Path("/tmp/jellynama-debug")
```

to:

```python
_DEBUG_DIR = Path("/tmp/jellygrab-debug")
```

- [ ] **Step 4: Replace FlareSolverr default session name**

In [sidecar/config.py:49](sidecar/config.py#L49), change:

```python
flaresolverr_session=os.getenv("FLARESOLVERR_SESSION", "jellynama"),
```

to:

```python
flaresolverr_session=os.getenv("FLARESOLVERR_SESSION", "jellygrab"),
```

- [ ] **Step 5: Verify no `jellynama` or `JellyNama` remain in Python source**

Run:
```bash
cd /Users/omidkarami/Projects/jellynama
grep -rnE "jellynama|JellyNama" sidecar/
```

Expected: empty output.

- [ ] **Step 6: Verify imports still resolve**

Run:
```bash
cd /Users/omidkarami/Projects/jellynama/sidecar
python3 -c "import main; print('ok')"
```

Expected: `ok`.

- [ ] **Step 7: Commit**

```bash
git add sidecar/
git commit -m "Rename Python project identifiers to jellygrab"
```

---

## Task 5: Rename C# plugin (namespace, classes, GUID, csproj, embedded resources)

Replace project-level `JellyNama` strings in C# source and rename the csproj + controller filenames. Regenerate the plugin GUID (a new project deserves a new identity).

**Files:**
- Rename: `jellyfin-plugin/Jellyfin.Plugin.JellyNama.csproj` → `jellyfin-plugin/Jellyfin.Plugin.JellyGrab.csproj`
- Rename: `jellyfin-plugin/JellyNamaController.cs` → `jellyfin-plugin/JellyGrabController.cs`
- Modify: `jellyfin-plugin/Plugin.cs`
- Modify: `jellyfin-plugin/PluginServiceRegistrator.cs`
- Modify: `jellyfin-plugin/InjectScriptService.cs`
- Modify: `jellyfin-plugin/Configuration/PluginConfiguration.cs`
- Modify: `jellyfin-plugin/Configuration/configPage.html`
- Modify: `jellyfin-plugin/manifest.json`
- Modify: `jellyfin-plugin/build.yaml`

- [ ] **Step 1: Generate a new plugin GUID**

Run:
```bash
python3 -c "import uuid; print(str(uuid.uuid4()))"
```

Record the output (referred to below as `<NEW_GUID>`). Example: `c4e2a8d1-93f7-4b20-a6f5-5e8c0d1b9a47`.

- [ ] **Step 2: Rename csproj and controller files via `git mv`**

```bash
cd /Users/omidkarami/Projects/jellynama
git mv jellyfin-plugin/Jellyfin.Plugin.JellyNama.csproj jellyfin-plugin/Jellyfin.Plugin.JellyGrab.csproj
git mv jellyfin-plugin/JellyNamaController.cs jellyfin-plugin/JellyGrabController.cs
```

- [ ] **Step 3: Update `Plugin.cs`**

In [jellyfin-plugin/Plugin.cs](jellyfin-plugin/Plugin.cs):

- `using Jellyfin.Plugin.JellyNama.Configuration;` → `using Jellyfin.Plugin.JellyGrab.Configuration;`
- `namespace Jellyfin.Plugin.JellyNama;` → `namespace Jellyfin.Plugin.JellyGrab;`
- `public override string Name => "JellyNama";` → `public override string Name => "JellyGrab";`
- `Guid.Parse("3a8d4f2e-7c1b-4e6a-9f8d-2b5e1a9c4d7e")` → `Guid.Parse("<NEW_GUID>")`
- The Description string: replace with `"A Jellyfin companion plugin that adds a downloader page wired to the JellyGrab sidecar service."`
- `Name = "JellyNamaJs"` → `Name = "JellyGrabJs"`
- `EmbeddedResourcePath = $"{GetType().Namespace}.Web.jellynama.js"` → `EmbeddedResourcePath = $"{GetType().Namespace}.Web.jellygrab.js"` (the file rename happens in Task 6)

- [ ] **Step 4: Update `PluginServiceRegistrator.cs`**

In [jellyfin-plugin/PluginServiceRegistrator.cs](jellyfin-plugin/PluginServiceRegistrator.cs):

- `namespace Jellyfin.Plugin.JellyNama;` → `namespace Jellyfin.Plugin.JellyGrab;`

- [ ] **Step 5: Update `InjectScriptService.cs`**

In [jellyfin-plugin/InjectScriptService.cs](jellyfin-plugin/InjectScriptService.cs):

- `namespace Jellyfin.Plugin.JellyNama;` → `namespace Jellyfin.Plugin.JellyGrab;`
- `Patches Jellyfin web's index.html to load JellyNama's inject.js into every page,` → `Patches Jellyfin web's index.html to load JellyGrab's inject.js into every page,`
- `private const string Marker = "<!-- JellyNamaInject -->";` → `private const string Marker = "<!-- JellyGrabInject -->";`
- `private const string ScriptTag = "<script defer src=\"/JellyNama/inject.js\"></script>";` → `private const string ScriptTag = "<script defer src=\"/JellyGrab/inject.js\"></script>";`
- All log messages: `"JellyNama: ..."` → `"JellyGrab: ..."`

- [ ] **Step 6: Update `Configuration/PluginConfiguration.cs`**

In [jellyfin-plugin/Configuration/PluginConfiguration.cs](jellyfin-plugin/Configuration/PluginConfiguration.cs):

- `namespace Jellyfin.Plugin.JellyNama.Configuration;` → `namespace Jellyfin.Plugin.JellyGrab.Configuration;`
- Doc comment: `The base URL of the JellyNama sidecar (FastAPI service).` → `The base URL of the JellyGrab sidecar (FastAPI service).`

- [ ] **Step 7: Update `Configuration/configPage.html`**

In [jellyfin-plugin/Configuration/configPage.html](jellyfin-plugin/Configuration/configPage.html):

- `<title>JellyNama</title>` → `<title>JellyGrab</title>`
- `id="JellyNamaConfigPage"` → `id="JellyGrabConfigPage"`
- `<h2 class="sectionTitle">JellyNama</h2>` → `<h2 class="sectionTitle">JellyGrab</h2>`
- `Where the JellyNama FastAPI sidecar is reachable from your browser` → `Where the JellyGrab FastAPI sidecar is reachable from your browser`
- `document.querySelector("#JellyNamaConfigPage")` → `document.querySelector("#JellyGrabConfigPage")`

- [ ] **Step 8: Rename `JellyNamaController` class and route**

In `jellyfin-plugin/JellyGrabController.cs` (the file just renamed):

- `namespace Jellyfin.Plugin.JellyNama;` → `namespace Jellyfin.Plugin.JellyGrab;`
- `[Route("JellyNama")]` → `[Route("JellyGrab")]`
- `public class JellyNamaController : ControllerBase` → `public class JellyGrabController : ControllerBase`
- `"Jellyfin.Plugin.JellyNama.Web.inject.js"` → `"Jellyfin.Plugin.JellyGrab.Web.inject.js"`

- [ ] **Step 9: Update the csproj**

In `jellyfin-plugin/Jellyfin.Plugin.JellyGrab.csproj`:

- `<RootNamespace>Jellyfin.Plugin.JellyNama</RootNamespace>` → `<RootNamespace>Jellyfin.Plugin.JellyGrab</RootNamespace>`
- `<EmbeddedResource Include="Web\jellynama.html" />` → `<EmbeddedResource Include="Web\jellygrab.html" />`
- `<EmbeddedResource Include="Web\jellynama.js" />` → `<EmbeddedResource Include="Web\jellygrab.js" />`

(The actual web file renames happen in Task 6.)

- [ ] **Step 10: Update `manifest.json`**

In [jellyfin-plugin/manifest.json](jellyfin-plugin/manifest.json), replace the entire content with (substituting `<NEW_GUID>`):

```json
[
  {
    "guid": "<NEW_GUID>",
    "name": "JellyGrab",
    "description": "A Jellyfin companion plugin that adds a downloader page wired to the JellyGrab sidecar service.",
    "overview": "JellyGrab — Jellyfin downloader plugin",
    "owner": "jellygrab",
    "category": "General",
    "versions": [
      {
        "version": "0.1.0.0",
        "changelog": "Initial release.",
        "targetAbi": "10.11.0.0",
        "sourceUrl": "https://example.com/jellygrab_0.1.0.0.zip",
        "checksum": "REPLACE_WITH_MD5_OF_ZIP",
        "timestamp": "2026-04-26T00:00:00Z"
      }
    ]
  }
]
```

- [ ] **Step 11: Update `build.yaml`**

In [jellyfin-plugin/build.yaml](jellyfin-plugin/build.yaml):

- `name: "JellyNama"` → `name: "JellyGrab"`
- The description block: replace `JellyNama adds a Dashboard page that talks to the JellyNama FastAPI sidecar` with `JellyGrab adds a Dashboard page that talks to the JellyGrab FastAPI sidecar`
- `owner: "jellynama"` → `owner: "jellygrab"`
- `- "Jellyfin.Plugin.JellyNama.dll"` → `- "Jellyfin.Plugin.JellyGrab.dll"`

- [ ] **Step 12: Verify no `JellyNama` or `jellynama` remain in C#/plugin source (excluding embedded JS/HTML files renamed in Task 6)**

Run:
```bash
cd /Users/omidkarami/Projects/jellynama
grep -rnE "JellyNama|jellynama" jellyfin-plugin/ --include="*.cs" --include="*.csproj" --include="*.json" --include="*.yaml" --include="*.html"
```

Expected: only matches inside `jellyfin-plugin/Web/jellynama.html` and `jellyfin-plugin/Web/jellynama.js` (handled in Task 6) and possibly inside `jellyfin-plugin/README.md` (handled in Task 9).

- [ ] **Step 13: Commit**

```bash
git add jellyfin-plugin/
git commit -m "Rename C# plugin to Jellyfin.Plugin.JellyGrab and regenerate GUID"
```

---

## Task 6: Rename frontend JS / HTML and UI strings

Rename the embedded web files and update DOM ids, marker attrs, and visible UI strings.

**Files:**
- Rename: `jellyfin-plugin/Web/jellynama.html` → `jellyfin-plugin/Web/jellygrab.html`
- Rename: `jellyfin-plugin/Web/jellynama.js` → `jellyfin-plugin/Web/jellygrab.js`
- Modify: `jellyfin-plugin/Web/jellygrab.html` (after rename)
- Modify: `jellyfin-plugin/Web/jellygrab.js` (after rename)
- Modify: `jellyfin-plugin/Web/inject.js`

- [ ] **Step 1: Rename web files**

```bash
cd /Users/omidkarami/Projects/jellynama
git mv jellyfin-plugin/Web/jellynama.html jellyfin-plugin/Web/jellygrab.html
git mv jellyfin-plugin/Web/jellynama.js jellyfin-plugin/Web/jellygrab.js
```

- [ ] **Step 2: Update `jellygrab.html` UI strings and script src**

In `jellyfin-plugin/Web/jellygrab.html`:

- `<title>JellyNama</title>` → `<title>JellyGrab</title>`
- `<h1>JellyNama</h1>` → `<h1>JellyGrab</h1>`
- `<script src="jellynama.js"></script>` → `<script src="jellygrab.js"></script>`

- [ ] **Step 3: Update `jellygrab.js` global**

In `jellyfin-plugin/Web/jellygrab.js`, change:

```javascript
const API_BASE = params.get("api") || window.JELLYNAMA_API || location.origin;
```

to:

```javascript
const API_BASE = params.get("api") || window.JELLYGRAB_API || location.origin;
```

- [ ] **Step 4: Update `inject.js`**

In [jellyfin-plugin/Web/inject.js](jellyfin-plugin/Web/inject.js):

- Header comment block: `JellyNama search-view injector` → `JellyGrab search-view injector`. Continue replacing every project-level `JellyNama` reference in the file's comments with `JellyGrab`.
- `const MARKER_ATTR = "data-jellynama-injected";` → `const MARKER_ATTR = "data-jellygrab-injected";`
- `const MODAL_ID = "jellynama-modal";` → `const MODAL_ID = "jellygrab-modal";`
- `banner.className = "jellynama-banner verticalSection";` → `banner.className = "jellygrab-banner verticalSection";`
- The modal heading HTML string: `JellyNama · 30nama search` → `JellyGrab · 30nama search`

- [ ] **Step 5: Verify nothing remains in the web folder**

Run:
```bash
cd /Users/omidkarami/Projects/jellynama
grep -rnE "JellyNama|jellynama|JELLYNAMA" jellyfin-plugin/Web/
```

Expected: empty output.

- [ ] **Step 6: Commit**

```bash
git add jellyfin-plugin/
git commit -m "Rename plugin web files and DOM ids to jellygrab"
```

---

## Task 7: Update infra files (docker-compose, install script, pyproject, env example, dockerignore)

Identifier replacement in deployment files.

**Files:**
- Modify: `docker-compose.yml`
- Modify: `install-plugin.sh`
- Modify: `pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Update `docker-compose.yml`**

In [docker-compose.yml](docker-compose.yml):

- Comment `# JellyNama plugin DLL is copied into ./jellyfin/config/plugins/JellyNama_0.1.0/` → `# JellyGrab plugin DLL is copied into ./jellyfin/config/plugins/JellyGrab_0.1.0/`
- All `jellynama-net` → `jellygrab-net`
- Service name `jellynama:` → `jellygrab:`
- `container_name: jellynama` → `container_name: jellygrab`
- `container_name: jellynama-flaresolverr` → `container_name: jellygrab-flaresolverr`
- Network definition `jellynama-net:` → `jellygrab-net:`

Run after editing:
```bash
cd /Users/omidkarami/Projects/jellynama
docker compose config > /dev/null
```

Expected: no errors. (This validates the YAML.)

- [ ] **Step 2: Update `install-plugin.sh`**

In [install-plugin.sh](install-plugin.sh):

- Comment `# Copies the locally-built JellyNama plugin DLL into Jellyfin's plugins dir` → `# Copies the locally-built JellyGrab plugin DLL into Jellyfin's plugins dir`
- `DST_DIR="jellyfin/config/plugins/JellyNama_0.1.0"` → `DST_DIR="jellyfin/config/plugins/JellyGrab_0.1.0"`
- The `echo` line: `Installed: $DST_DIR/Jellyfin.Plugin.JellyNama.dll` → `Installed: $DST_DIR/Jellyfin.Plugin.JellyGrab.dll`
- Any reference to the source DLL path needs to match: open the file and update any other `Jellyfin.Plugin.JellyNama.dll` strings to `Jellyfin.Plugin.JellyGrab.dll`.

- [ ] **Step 3: Update `pyproject.toml`**

In [pyproject.toml](pyproject.toml):

- `name = "jellynama"` → `name = "jellygrab"`
- `description = "Jellyfin companion sidecar for searching and downloading from 30nama.com"` → `description = "JellyGrab — a Jellyfin downloader sidecar with pluggable scrapers (30nama scraper bundled)."`

- [ ] **Step 4: Update `.env.example`**

The current `.env.example` has no `JELLYNAMA_*` vars, so no rename is required. Verify:

```bash
cd /Users/omidkarami/Projects/jellynama
grep -E "JELLYNAMA|jellynama" .env.example
```

Expected: empty output. If anything appears, replace `JELLYNAMA` with `JELLYGRAB` and `jellynama` with `jellygrab`.

- [ ] **Step 5: Verify infra files clean**

Run:
```bash
cd /Users/omidkarami/Projects/jellynama
grep -nE "jellynama|JellyNama" docker-compose.yml install-plugin.sh pyproject.toml .env.example .dockerignore 2>/dev/null
```

Expected: empty output.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml install-plugin.sh pyproject.toml .env.example
git commit -m "Rename docker-compose, install script, pyproject to jellygrab"
```

---

## Task 8: Update `.github/workflows/build-plugin.yml`

Update CI artifact names and DLL filename references after the plugin rename.

**Files:**
- Modify: `.github/workflows/build-plugin.yml`

- [ ] **Step 1: Update DLL existence check, zip name, and artifact name**

In [.github/workflows/build-plugin.yml](.github/workflows/build-plugin.yml):

- `run: test -f publish/Jellyfin.Plugin.JellyNama.dll` → `run: test -f publish/Jellyfin.Plugin.JellyGrab.dll`
- `zip -j "../jellynama-jellyfin-${{ matrix.jellyfin }}.zip" Jellyfin.Plugin.JellyNama.dll` → `zip -j "../jellygrab-jellyfin-${{ matrix.jellyfin }}.zip" Jellyfin.Plugin.JellyGrab.dll`
- `name: jellynama-jellyfin-${{ matrix.jellyfin }}` → `name: jellygrab-jellyfin-${{ matrix.jellyfin }}`
- `path: jellyfin-plugin/jellynama-jellyfin-${{ matrix.jellyfin }}.zip` → `path: jellyfin-plugin/jellygrab-jellyfin-${{ matrix.jellyfin }}.zip`

Open the file and inspect remaining steps for any other `JellyNama` / `jellynama` references; replace them with `JellyGrab` / `jellygrab`.

- [ ] **Step 2: Verify clean**

Run:
```bash
cd /Users/omidkarami/Projects/jellynama
grep -nE "jellynama|JellyNama" .github/workflows/build-plugin.yml
```

Expected: empty output.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/build-plugin.yml
git commit -m "Update build-plugin workflow to jellygrab artifacts"
```

---

## Task 9: Rewrite top-level `README.md` with framework framing + DISCLAIMER

Replace the README with one that leads with the generic-framework story, lists the bundled 30nama scraper as one example, and includes a clear legal disclaimer.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md` with the new framing**

Create `/Users/omidkarami/Projects/jellynama/README.md` (full overwrite):

````markdown
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

| Plugin | Target | Build flag | ABI tag |
|--------|--------|------------|---------|
| JellyGrab | Jellyfin | .NET | targetAbi |

To rebuild for a different ABI, bump `Jellyfin.Controller` and `Jellyfin.Model`
versions in
[jellyfin-plugin/Jellyfin.Plugin.JellyGrab.csproj](jellyfin-plugin/Jellyfin.Plugin.JellyGrab.csproj)
(or pass `-p:JellyfinVersion=X.Y.Z` at build time).

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
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Rewrite README around generic-framework framing with disclaimer"
```

---

## Task 10: Rewrite `jellyfin-plugin/README.md`

The plugin sub-README needs the same reframing.

**Files:**
- Modify: `jellyfin-plugin/README.md`

- [ ] **Step 1: Replace `jellyfin-plugin/README.md`**

Create `/Users/omidkarami/Projects/jellynama/jellyfin-plugin/README.md` (full overwrite):

````markdown
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
````

- [ ] **Step 2: Commit**

```bash
git add jellyfin-plugin/README.md
git commit -m "Rewrite plugin README for jellygrab"
```

---

## Task 11: Update `CLAUDE.md`

Refresh project guidance to match the new name and framing.

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update name and one-line description**

In [CLAUDE.md](CLAUDE.md):

- `# CLAUDE.md` (heading) — keep
- `Guidance for Claude Code when working in this repo.` — keep
- The "What This Is" paragraph: replace `JellyNama is a Jellyfin companion that searches 30nama.com (Persian media site), downloads .mkv/.mp4 files via direct HTTP, and triggers a Jellyfin library refresh.` with `JellyGrab is a Jellyfin downloader companion: a FastAPI sidecar plus a Jellyfin plugin. Scrapers are pluggable under sidecar/scrapers/<name>/. One reference scraper (sidecar/scrapers/nama/) targets 30nama.com (a Persian-language media site).`
- Add a new "Don't" bullet at the bottom of the existing "Don't" section: `Don't reframe the project away from "generic downloader framework with one example scraper". The narrative is intentional — see docs/superpowers/specs/2026-04-29-public-release-design.md.`
- Replace any other `JellyNama` reference in the file with `JellyGrab` and any `jellynama` with `jellygrab`.

Run:
```bash
cd /Users/omidkarami/Projects/jellynama
grep -nE "JellyNama|jellynama" CLAUDE.md
```

Expected: empty output.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Update CLAUDE.md to JellyGrab framing"
```

---

## Task 12: Add `CONTRIBUTING.md` and `docs/scrapers.md`

The README links to `docs/scrapers.md`; create it. Also add a brief contributing note.

**Files:**
- Create: `CONTRIBUTING.md`
- Create: `docs/scrapers.md`

- [ ] **Step 1: Create `CONTRIBUTING.md`**

Create `/Users/omidkarami/Projects/jellynama/CONTRIBUTING.md`:

````markdown
# Contributing

PRs welcome. The most useful contributions are:

- New scrapers under `sidecar/scrapers/<name>/`. See [docs/scrapers.md](docs/scrapers.md).
- Bug fixes, especially around Jellyfin API edge cases or download robustness.
- Documentation improvements.

## Ground rules

- Python: async/await only inside the sidecar (FastAPI + httpx). No sync I/O
  in route handlers.
- No new runtime dependencies (Redis, Celery, a database) — the in-memory job
  queue is intentional.
- No authentication — the sidecar is meant to run on a private Docker network.
- The Jellyfin plugin frontend is vanilla JS. No build step, no React, no TS.

## Development

1. `cp .env.example .env` and fill in values
2. `docker compose up -d`
3. Iterate. The sidecar auto-reloads if you mount the source as a volume.

## Code style

The Python side uses `ruff` with the config in `pyproject.toml`. Run
`ruff check sidecar/` before opening a PR.
````

- [ ] **Step 2: Create `docs/scrapers.md`**

Create `/Users/omidkarami/Projects/jellynama/docs/scrapers.md`:

````markdown
# Writing a Scraper

A JellyGrab scraper is a Python module under `sidecar/scrapers/<name>/`
that exposes four async functions matching the `Scraper` protocol in
[sidecar/scrapers/__init__.py](../sidecar/scrapers/__init__.py):

```python
async def startup() -> None: ...
async def shutdown() -> None: ...
async def search(query: str) -> list[SearchResult]: ...
async def get_download_options(detail_url: str) -> list[DownloadOption]: ...
```

Where `SearchResult` and `DownloadOption` are simple objects with the
attributes used by the sidecar's API (see
`sidecar/scrapers/nama/scraper.py` for the reference implementation).

## Wiring it in

The sidecar currently imports a single scraper directly:

```python
# sidecar/main.py
from scrapers import nama as scraper
```

To swap scrapers, change that import. A future revision may make this
configurable via env var; for now, fork the line.

## Reference: the `nama` scraper

[sidecar/scrapers/nama/](../sidecar/scrapers/nama/) is the bundled
reference implementation. It scrapes 30nama.com using a cookie-based
session and FlareSolverr for Cloudflare bypass. Use it as a template,
not a strict pattern — most sites won't need FlareSolverr.

## Things a good scraper does

- Returns a `kind` field (`"movie"`, `"series"`, `"unknown"`) on each result
  so the UI can group correctly.
- Handles network errors gracefully — return an empty list rather than
  raising on a failed search.
- Caches expensive lookups inside `startup()` if the source allows it.
````

- [ ] **Step 3: Commit**

```bash
git add CONTRIBUTING.md docs/scrapers.md
git commit -m "Add CONTRIBUTING and scrapers writing guide"
```

---

## Task 13: Resolve dangling `docs/plan.md` reference

The old `README.md` linked to `docs/plan.md`, which isn't tracked. Task 9 already removed that link. Verify nothing else references it.

**Files:**
- Read-only: full repo

- [ ] **Step 1: Verify no `docs/plan.md` references remain**

Run:
```bash
cd /Users/omidkarami/Projects/jellynama
git grep -n "docs/plan.md"
```

Expected: empty output. If something is found, remove the reference (or, if the user has a real `docs/plan.md` they want tracked, add it to the repo — defer to the user).

- [ ] **Step 2: No commit unless changes were needed.**

---

## Task 14: Smoke test the full stack

Confirm the rename didn't break anything. This replaces unit tests for this rename-only change.

**Files:**
- None (operational)

- [ ] **Step 1: Build and start the stack**

```bash
cd /Users/omidkarami/Projects/jellynama
docker compose down -v --remove-orphans
docker compose build --no-cache jellygrab
docker compose up -d
```

Expected: services come up. `docker compose ps` shows `jellygrab` and `jellygrab-flaresolverr` running.

- [ ] **Step 2: Sidecar health check**

Run:
```bash
curl -fsS http://localhost:8765/api/health
```

Expected: `{"ok":true}`. Investigate logs (`docker compose logs jellygrab`) if not.

- [ ] **Step 3: OpenAPI title check**

Run:
```bash
curl -fsS http://localhost:8765/openapi.json | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['info']['title'])"
```

Expected: `JellyGrab Sidecar`.

- [ ] **Step 4: Search smoke test (requires `NAMA_COOKIE` configured)**

If the user has `NAMA_COOKIE` set in `.env`:

```bash
curl -fsS "http://localhost:8765/api/search?q=interstellar" | python3 -c "import sys, json; d=json.load(sys.stdin); print(f'hits: {len(d)}')"
```

Expected: a non-zero hit count (or zero with no error). If `NAMA_COOKIE` isn't set, skip this step and note it in the smoke-test results.

- [ ] **Step 5: Build the Jellyfin plugin**

```bash
cd /Users/omidkarami/Projects/jellynama/jellyfin-plugin
dotnet publish Jellyfin.Plugin.JellyGrab.csproj -c Release -o publish
test -f publish/Jellyfin.Plugin.JellyGrab.dll
```

Expected: exit 0; the DLL exists. If `dotnet` isn't installed locally, this step can be deferred to CI verification (Task 15).

- [ ] **Step 6: Tear down**

```bash
cd /Users/omidkarami/Projects/jellynama
docker compose down
```

- [ ] **Step 7: No commit (operational verification only).**

---

## Task 15: GitHub setup — push private, verify CI, flip public

Final step. Stage the repo on GitHub privately first so any breakage in CI is caught before the world sees it, then flip to public.

**Files:**
- None (operational)

- [ ] **Step 1: Decide the GitHub username/org and repo name**

The repo name should be `jellygrab`. Confirm with the user which account or org owns it before pushing.

- [ ] **Step 2: Create a PRIVATE repo on GitHub**

Run (replace `<owner>` with the agreed account/org):

```bash
gh repo create <owner>/jellygrab --private --description "A Jellyfin companion that adds pluggable search-and-download. Bundled with one reference scraper." --source=/Users/omidkarami/Projects/jellynama --remote=origin --push=false
```

Expected: repo created, `origin` remote added.

- [ ] **Step 3: Push current branch**

```bash
cd /Users/omidkarami/Projects/jellynama
git push -u origin main
```

Expected: push succeeds.

- [ ] **Step 4: Wait for CI to pass**

Run:
```bash
gh run watch
```

Expected: the `build-plugin` workflow completes successfully across all matrix entries. If CI fails, fix the underlying issue and push again before continuing — don't flip to public with broken CI.

- [ ] **Step 5: Add repo topics**

```bash
gh repo edit <owner>/jellygrab --add-topic jellyfin --add-topic self-hosted --add-topic python --add-topic fastapi --add-topic docker --add-topic plugin
```

- [ ] **Step 6: Add issue templates (optional)**

If the user agrees, create the two templates below. If they want to skip, mark this step done and continue.

Create `/Users/omidkarami/Projects/jellynama/.github/ISSUE_TEMPLATE/bug_report.md`:

```markdown
---
name: Bug report
about: Report a problem with JellyGrab
labels: bug
---

**What happened?**

**What did you expect?**

**Steps to reproduce:**

1.
2.
3.

**Environment:**
- Jellyfin version:
- JellyGrab version:
- Active scraper:
- Docker / native:

**Logs (sidecar + plugin if relevant):**

```

Create `/Users/omidkarami/Projects/jellynama/.github/ISSUE_TEMPLATE/feature_request.md`:

```markdown
---
name: Feature request
about: Suggest an enhancement
labels: enhancement
---

**Problem this would solve:**

**Proposed approach:**

**Alternatives considered:**
```

Commit:
```bash
cd /Users/omidkarami/Projects/jellynama
git add .github/ISSUE_TEMPLATE/
git commit -m "Add bug and feature issue templates"
git push
```

- [ ] **Step 7: Flip the repo to public**

Only do this once the user has confirmed the README, disclaimer, and CI all look good.

```bash
gh repo edit <owner>/jellygrab --visibility public --accept-visibility-change-consequences
```

Expected: repo is now public.

- [ ] **Step 8: Final verification**

Visit `https://github.com/<owner>/jellygrab` in a browser. Confirm:
- README renders cleanly with the framework framing on top
- Disclaimer section is visible
- LICENSE file is detected by GitHub (the repo page shows "MIT")
- CI badge (if added) is green
- No `JellyNama` / `jellynama` strings appear in the rendered README

- [ ] **Step 9: No commit (operational).**

---

## Done criteria

- All 15 tasks above completed
- `git grep -nE "JellyNama|jellynama|JELLYNAMA"` returns empty across the repo (excluding `docs/superpowers/` history records)
- `docker compose up` starts cleanly under the new names
- The plugin builds and produces `Jellyfin.Plugin.JellyGrab.dll`
- The repo is public on GitHub with MIT license, disclaimer, and green CI
