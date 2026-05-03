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

## Pull request checks and approvals

`main` is protected by a GitHub ruleset. Every PR must pass the required
`CI gate` workflow, which always runs and covers the merge-blocking checks:

- Python lint, compile, and tests
- GitHub Actions workflow lint
- Jellyfin plugin builds for the supported 10.10/net8 and 10.11/net9 ABIs

Other workflows may still run as path-filtered or release-specific feedback,
but `CI gate` is the stable required check. This avoids required checks being
left pending when a path-filtered workflow does not run.

CODEOWNER review is required before merge, and review threads must be
resolved. Repository admins may bypass PR rules when needed for solo-maintainer
work, but bypasses should be explicit and limited to cases where the required
checks have passed.

## Releases

Releases are intentionally manual. Release workflows may generate manifest PRs
for plugin catalog updates, but those PRs still need CODEOWNER approval before
auto-merge can complete. If the PR author is GitHub Actions or the sole
maintainer, a repository admin may use the ruleset bypass after verifying the
required checks. Do not add a maintainer PAT or bot bypass for release
automation.

## Pre-commit hooks (recommended)

`pre-commit` is configured in `.pre-commit-config.yaml`. After cloning:

```bash
uv sync --group dev          # installs pre-commit alongside ruff/pytest
uv run pre-commit install                       # runs ruff + actionlint + whitespace hooks on `git commit`
uv run pre-commit install --hook-type pre-push  # runs pytest on `git push`
```

The same checks run in the required `CI gate`, so this is purely to shorten
the feedback loop locally — you can still bypass with `--no-verify` when you
need to.
