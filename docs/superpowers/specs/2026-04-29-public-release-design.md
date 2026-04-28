# Public Release Design — JellyNama → JellyGrab

**Date:** 2026-04-29
**Status:** Approved, pending implementation plan

## Goal

Prepare the repository for public release on GitHub with a lower legal/community
profile, by reframing the project as a generic Jellyfin downloader framework
that ships with one example scraper, rather than as a 30nama-specific tool.

## Non-Goals

- No real refactor of the scraper architecture. The `Scraper` interface is a
  thin protocol describing what the existing `scraper.py` already does.
- No second working scraper. The framing is "scrapers are pluggable"; no extra
  scraper is added in this release.
- No new auth, no DB, no queue replacement. The CLAUDE.md constraints stand.

## Strategy: B-lite

Three levers, executed together:

1. **Rename** the project to `jellygrab` everywhere it appears as a project
   identifier. Code that specifically refers to 30nama (cookies, session,
   scraper class names) keeps `nama` — it correctly identifies *that scraper*.
2. **Reorganize** the 30nama code under `sidecar/scrapers/nama/` and add a
   `Scraper` protocol stub so the directory layout matches the framing.
3. **Rewrite** the README to lead with the framework story; the 30nama scraper
   becomes a "Included scrapers" subsection.

No business logic changes. The runtime behavior of the system after this work
is identical to before.

## Naming Rules

- Project identifier: `jellynama` / `JellyNama` / `Nama` → `jellygrab` /
  `JellyGrab` / `Grab`.
- 30nama-scoped identifiers stay as `nama` (e.g. `nama_session.py`,
  `nama_cookies_file`, `NamaScraper`).
- Env vars: `JELLYFIN_URL`, `JELLYFIN_API_KEY`, `DOWNLOAD_DIR` stay unchanged.
  Any `JELLYNAMA_*` env vars become `JELLYGRAB_*`.
- C# plugin GUID is regenerated (a new project deserves a new GUID).

## Directory Reorg

Before:

```
sidecar/
  scraper.py
  nama_session.py
  flaresolverr_client.py
  …
```

After:

```
sidecar/
  scrapers/
    __init__.py          # exports Scraper protocol
    nama/
      __init__.py
      scraper.py
      session.py
      flaresolverr.py
  …
```

The `Scraper` protocol in `sidecar/scrapers/__init__.py` is a few-line
`typing.Protocol` matching what `scraper.py` already exposes (search +
get_download_url shapes). No behavior change.

## Public-Release Checklist

### Legal / safety

1. Add `LICENSE` (MIT).
2. Add a `DISCLAIMER` section to the README: users are responsible for the
   legality of what they download; project is a generic framework; no content
   is hosted or distributed by this repo.
3. Audit git history for secrets — `.env`, cookies, API keys ever committed.
4. Verify `.gitignore` covers `secrets/`, `media/`, `jellyfin/`, `.env`,
   `*_cookies.json`.
5. Strip personal data: hardcoded paths, username, Jellyfin URL, anything in
   committed config.

### Repo hygiene

6. Rewrite `README.md` around the framework framing; move 30nama to a "Included
   scrapers" subsection; add screenshots / GIF of the UI.
7. Rewrite `jellyfin-plugin/README.md` to match.
8. Update `CLAUDE.md` references to the new name.
9. Resolve the dangling `docs/plan.md` reference (file isn't tracked; either
   add it or remove the link).
10. Add `CONTRIBUTING.md` stub — one paragraph, points at the scraper docs.
11. Add `docs/scrapers.md` — short "Writing your own scraper" doc pointing at
    the `Scraper` protocol.
12. Confirm `.github/workflows/build-plugin.yml` still works after the rename.

### Rename execution

13. Bulk-replace identifiers in the sidecar (Python).
14. Bulk-replace identifiers in the plugin (C#) and regenerate the plugin GUID.
15. Bulk-replace in frontend JS/HTML and UI strings (dashboard menu label,
    injected button label).
16. Update `docker-compose.yml`, `Dockerfile`, `pyproject.toml`,
    `install-plugin.sh`.
17. Move `sidecar/scraper.py`, `nama_session.py`, `flaresolverr_client.py`
    into `sidecar/scrapers/nama/`; add the `Scraper` protocol stub.
18. Smoke test: `docker compose up`, run a search, run a download, confirm
    Jellyfin library refresh.

### GitHub setup

19. Push to a private repo first; verify CI; then flip to public.
20. Add repo description and topics (`jellyfin`, `self-hosted`, `python`,
    `fastapi`).
21. Optional: issue templates (`bug_report.md`, `feature_request.md`).

## Risks

- **History leaks.** Step 3 must run before publishing. If a secret was ever
  committed, rotating it is mandatory; rewriting history is preferred.
- **Plugin GUID change** invalidates existing installs. Acceptable — there are
  no public installs yet.
- **Reframing remains thin.** Anyone reading the source will see a 30nama tool
  with one stub protocol. This is accepted (B-lite, not B-real).
