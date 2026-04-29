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
