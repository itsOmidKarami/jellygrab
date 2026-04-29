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
