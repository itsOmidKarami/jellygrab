"""Periodic ping against 30nama via FlareSolverr to keep the session warm.

FlareSolverr holds the live browser session that solved Cloudflare. Pinging
the homepage through it serves three purposes: it keeps FS's solved clearance
fresh, it pulls any rotated cookies back into our on-disk jar so the
curl_cffi-based downloader stays valid, and it acts as a health probe — when
the ping fails we surface that to the operator.
"""

import asyncio
import json
import logging
import time
from urllib.parse import unquote

from scrapers import nama as scraper
from scrapers.nama import flaresolverr as fs
from scrapers.nama import session as nama_session
from config import settings
from session_state import status

log = logging.getLogger("jellynama.keepalive")
log.setLevel(logging.INFO)
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(_h)
    log.propagate = False


def _is_logged_in(jar: dict[str, str]) -> bool | None:
    """30nama stores `clientSession` as URL-encoded JSON; logged-in users have
    a non-empty `usertoken`. Returns None if the cookie isn't present at all."""
    raw = jar.get("clientSession")
    if not raw:
        return None
    try:
        data = json.loads(unquote(raw))
        return bool(data.get("usertoken"))
    except Exception:
        return None


async def _ping_once() -> None:
    try:
        sol = await fs.request_get(settings.nama_base_url)
    except Exception as exc:
        status.last_check_at = time.time()
        status.healthy = False
        status.error = str(exc)
        status.note = "FlareSolverr request failed"
        log.exception("keepalive: FS request failed")
        return

    http_status = int(sol.get("status") or 0)
    fresh_jar = fs.cookies_to_jar(sol.get("cookies") or [])
    if fresh_jar:
        nama_session.merge_cookies(fresh_jar)
        scraper._cookie_jar.cache_clear()
    ua = (sol.get("userAgent") or "").strip()
    if ua:
        nama_session.set_user_agent(ua)

    jar = scraper.cookie_jar()
    logged_in = _is_logged_in(jar)
    status.last_check_at = time.time()
    status.cookies_count = len(jar)
    status.cf_clearance_present = bool(jar.get("cf_clearance"))
    status.logged_in = logged_in

    if http_status >= 400 or http_status == 0:
        status.healthy = False
        status.note = f"HTTP {http_status} via FlareSolverr"
        status.error = None
        log.warning(
            "keepalive: 30nama ping unhealthy via FS (status=%s, cookies=%d)",
            http_status, len(jar),
        )
        return

    status.healthy = True
    status.error = None
    status.note = (
        "logged in" if logged_in
        else "anonymous (no session)" if logged_in is False
        else "ok"
    )
    cf = jar.get("cf_clearance", "")
    log.info(
        "keepalive: 30nama ping ok via FS (status=%s, cookies=%d, cf_clearance=%s, logged_in=%s)",
        http_status, len(jar), (cf[:8] + "…") if cf else "absent", logged_in,
    )


async def loop() -> None:
    interval = settings.keepalive_interval_sec
    if interval <= 0:
        log.info("keepalive: disabled (KEEPALIVE_INTERVAL_SEC=%s)", interval)
        return
    log.info("keepalive: pinging 30nama (via FlareSolverr) every %ss", interval)
    await asyncio.sleep(min(60, interval))
    while True:
        try:
            await _ping_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            status.last_check_at = time.time()
            status.healthy = False
            status.error = str(exc)
            status.note = "ping failed"
            log.exception("keepalive: ping failed")
        await asyncio.sleep(interval)
