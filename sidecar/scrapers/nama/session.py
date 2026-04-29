"""Holds the current 30nama session credentials minted by FlareSolverr.

The cookies file (NAMA_COOKIES_FILE) is still the single source of truth for
the cookie jar — both for human inspection and for curl_cffi-driven downloads.
This module just adds a sibling file (`<cookies-file>.ua`) that stores the
exact User-Agent FlareSolverr used when it solved the challenge, so our own
HTTP requests can present the matching UA.

Why match the UA: cf_clearance is partially fingerprint-bound. Replaying the
clearance from an arbitrary UA gets it rejected; replaying from FlareSolverr's
exact UA (combined with curl_cffi's Chrome-impersonating TLS) is what lets the
sidecar make raw requests without going through FS for every byte.
"""

import json
import logging
from pathlib import Path

from config import settings

log = logging.getLogger("jellygrab.nama_session")
log.setLevel(logging.INFO)
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(_h)
    log.propagate = False


def _ua_path() -> Path | None:
    target = settings.nama_cookies_file
    if not target:
        return None
    return target.with_name(target.name + ".ua")


def get_user_agent() -> str:
    """Return the FS-minted UA, falling back to the configured default."""
    p = _ua_path()
    if p and p.exists():
        try:
            ua = p.read_text().strip()
            if ua:
                return ua
        except Exception:
            pass
    return settings.nama_user_agent


def set_user_agent(ua: str) -> None:
    p = _ua_path()
    if not p or not ua:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(ua.strip() + "\n")


def merge_cookies(fresh: dict[str, str]) -> dict[str, str]:
    """Merge fresh cookies into the on-disk jar. Returns the merged jar.

    Newer values win — Cloudflare rotates `cf_clearance` and the site rotates
    its session cookies, so we always trust the latest minted values.
    """
    target = settings.nama_cookies_file
    if not target:
        return fresh
    existing: dict[str, str] = {}
    if target.exists():
        try:
            existing = json.loads(target.read_text())
        except Exception:
            existing = {}
    merged = {**existing, **fresh}
    if merged != existing:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
    return merged
