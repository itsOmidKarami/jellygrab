"""Thin async wrapper around the FlareSolverr HTTP API.

FlareSolverr runs a real Chromium that solves Cloudflare challenges. We use it
in two ways:

1. As a *session minter*: hit the homepage through FS, copy the resulting
   cookies + UA out, then make our own requests via curl_cffi (which
   impersonates Chrome's TLS/JA3) using those credentials. CF accepts the
   transplanted clearance because curl_cffi's fingerprint is close enough to a
   real Chrome and we share the docker host's egress IP with FS.

2. As a *fallback fetcher* for pages where curl_cffi-with-FS-cookies still
   gets challenged — we just ask FS to fetch the URL and return the rendered
   HTML.

FS exposes a single endpoint, POST /v1, with a `cmd` field. We persist a named
session (`flaresolverr_session`) so the solved clearance is reused across calls
instead of being re-minted on every request.
"""

import asyncio
import json
import logging
from typing import Any

import httpx

from config import settings

log = logging.getLogger("jellygrab.flaresolverr")
log.setLevel(logging.INFO)
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(_h)
    log.propagate = False


class FlareSolverrError(RuntimeError):
    pass


_session_lock = asyncio.Lock()
_session_ready = False


async def _post(payload: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
    url = f"{settings.flaresolverr_url}/v1"
    if timeout is None:
        # FS's internal timeout is `maxTimeout` in ms — give httpx a few extra
        # seconds so we always see FS's structured error rather than a transport timeout.
        timeout = (settings.flaresolverr_timeout_ms / 1000.0) + 10
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


async def _ensure_session() -> None:
    """Create the named FS session once per sidecar lifetime. Idempotent — FS
    returns an error if the session already exists, which we treat as success."""
    global _session_ready
    async with _session_lock:
        if _session_ready:
            return
        body = await _post({"cmd": "sessions.create", "session": settings.flaresolverr_session})
        if body.get("status") not in ("ok", "error"):
            raise FlareSolverrError(f"unexpected sessions.create response: {body}")
        # "error" with message "Session already exists" is fine.
        if body.get("status") == "error" and "already exists" not in (body.get("message") or "").lower():
            raise FlareSolverrError(f"sessions.create failed: {body.get('message')}")
        _session_ready = True
        log.info("flaresolverr: session %r ready", settings.flaresolverr_session)


async def reset_session() -> None:
    """Tear down + recreate the FS session — useful when its cached clearance
    has gone stale and we want a fresh solve."""
    global _session_ready
    async with _session_lock:
        try:
            await _post({"cmd": "sessions.destroy", "session": settings.flaresolverr_session})
        except Exception as exc:
            log.warning("flaresolverr: sessions.destroy failed (continuing): %s", exc)
        _session_ready = False
    await _ensure_session()


async def _request(method: str, url: str, post_data: str | None = None) -> dict[str, Any]:
    await _ensure_session()
    payload: dict[str, Any] = {
        "cmd": f"request.{method}",
        "url": url,
        "maxTimeout": settings.flaresolverr_timeout_ms,
        "session": settings.flaresolverr_session,
    }
    if method == "post":
        payload["postData"] = post_data or ""
    body = await _post(payload)
    if body.get("status") != "ok":
        raise FlareSolverrError(f"request.{method} {url} failed: {body.get('message')}")
    sol = body.get("solution") or {}
    if not sol:
        raise FlareSolverrError(f"request.{method} {url} returned no solution: {body}")
    log.info(
        "flaresolverr: %s %s -> %s (cookies=%d, ua_len=%d, body_len=%d)",
        method.upper(), url, sol.get("status"), len(sol.get("cookies") or []),
        len(sol.get("userAgent") or ""), len(sol.get("response") or ""),
    )
    return sol


async def request_get(url: str) -> dict[str, Any]:
    return await _request("get", url)


async def request_post(url: str, post_data: str = "") -> dict[str, Any]:
    return await _request("post", url, post_data=post_data)


def cookies_to_jar(cookies: list[dict]) -> dict[str, str]:
    """Filter FS-returned cookies down to the 30nama-domain ones, as a flat jar."""
    jar: dict[str, str] = {}
    for c in cookies or []:
        domain = c.get("domain") or ""
        if "30nama.com" not in domain:
            continue
        name = c.get("name")
        value = c.get("value")
        if name and value is not None:
            jar[str(name)] = str(value)
    return jar


def dump_cookies_for_debug(cookies: list[dict]) -> str:
    """Compact representation of a cookie list, safe to log."""
    return json.dumps(
        [{"name": c.get("name"), "domain": c.get("domain"), "len": len(str(c.get("value", "")))}
         for c in (cookies or [])],
        ensure_ascii=False,
    )
