"""Periodic ping against 30nama to keep our session warm.

Cloudflare's `cf_clearance` cookie expires on a fixed schedule and won't
extend just by being used, but the site's own session/auth cookies do
have sliding expiration — so visiting the homepage at a regular cadence
keeps those alive. A ping also acts as a health probe: if Cloudflare
puts up a challenge or our cookies are stale, we log it loudly so the
operator knows to refresh `30nama_cookies.json`.
"""

import asyncio
import json
import logging
import time
from urllib.parse import unquote

from config import settings
from scraper import _new_context, persist_cookies
from session_state import status

log = logging.getLogger("jellynama.keepalive")
log.setLevel(logging.INFO)
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(_h)
    log.propagate = False


def _is_logged_in(jar: dict[str, str]) -> bool | None:
    """30nama stores `clientSession` as URL-encoded JSON; logged-in users have a
    non-empty `usertoken`. Returns None if the cookie isn't present at all."""
    raw = jar.get("clientSession")
    if not raw:
        return None
    try:
        data = json.loads(unquote(raw))
        return bool(data.get("usertoken"))
    except Exception:
        return None


async def _ping_once() -> None:
    ctx = await _new_context()
    try:
        page = await ctx.new_page()
        resp = await page.goto(settings.nama_base_url, wait_until="domcontentloaded", timeout=20000)
        http_status = resp.status if resp else 0
        title = (await page.title()) or ""
        # Cloudflare's challenge-platform beacon is on every protected page, so we
        # detect the interstitial by stricter markers: HTTP 403, the literal
        # "Just a moment" page title, or an explicit challenge form.
        challenge = (
            http_status == 403
            or "just a moment" in title.lower()
            or await page.locator("form#challenge-form, #cf-please-wait").count() > 0
        )
        if http_status >= 400 or challenge:
            status.last_check_at = time.time()
            status.healthy = False
            status.note = (
                "Cloudflare challenge — refresh cookies"
                if challenge
                else f"HTTP {http_status}"
            )
            status.error = None
            log.warning(
                "keepalive: 30nama ping unhealthy (status=%s, title=%r) — refresh cookies",
                http_status, title,
            )
            return

        jar = await persist_cookies(ctx)
        logged_in = _is_logged_in(jar)
        status.last_check_at = time.time()
        status.healthy = True
        status.logged_in = logged_in
        status.cf_clearance_present = bool(jar.get("cf_clearance"))
        status.cookies_count = len(jar)
        status.error = None
        status.note = (
            "logged in" if logged_in
            else "anonymous (no session)" if logged_in is False
            else "ok"
        )
        cf = jar.get("cf_clearance", "")
        log.info(
            "keepalive: 30nama ping ok (status=%s, cookies=%d, cf_clearance=%s, logged_in=%s)",
            http_status, len(jar), (cf[:8] + "…") if cf else "absent", logged_in,
        )
    finally:
        await ctx.close()


async def loop() -> None:
    interval = settings.keepalive_interval_sec
    if interval <= 0:
        log.info("keepalive: disabled (KEEPALIVE_INTERVAL_SEC=%s)", interval)
        return
    log.info("keepalive: pinging 30nama every %ss", interval)
    # Initial delay so the sidecar has a chance to warm up before the first ping.
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
