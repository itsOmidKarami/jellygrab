"""Periodic ping against 30nama to keep our session warm.

Cloudflare's `cf_clearance` cookie expires on a fixed schedule and won't
extend just by being used, but the site's own session/auth cookies do
have sliding expiration — so visiting the homepage at a regular cadence
keeps those alive. A ping also acts as a health probe: if Cloudflare
puts up a challenge or our cookies are stale, we log it loudly so the
operator knows to refresh `30nama_cookies.json`.
"""

import asyncio
import logging

from config import settings
from scraper import _new_context, persist_cookies

log = logging.getLogger("jellynama.keepalive")
log.setLevel(logging.INFO)
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(_h)
    log.propagate = False


async def _ping_once() -> None:
    ctx = await _new_context()
    try:
        page = await ctx.new_page()
        resp = await page.goto(settings.nama_base_url, wait_until="domcontentloaded", timeout=20000)
        status = resp.status if resp else 0
        title = (await page.title()) or ""
        # Cloudflare's challenge-platform beacon is on every protected page, so we
        # detect the interstitial by stricter markers: HTTP 403, the literal
        # "Just a moment" page title, or an explicit challenge form.
        challenge = (
            status == 403
            or "just a moment" in title.lower()
            or await page.locator("form#challenge-form, #cf-please-wait").count() > 0
        )
        if status >= 400 or challenge:
            log.warning(
                "keepalive: 30nama ping unhealthy (status=%s, title=%r) — refresh cookies",
                status, title,
            )
        else:
            jar = await persist_cookies(ctx)
            cf = jar.get("cf_clearance", "")
            log.info(
                "keepalive: 30nama ping ok (status=%s, cookies=%d, cf_clearance=%s)",
                status, len(jar), (cf[:8] + "…") if cf else "absent",
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
        except Exception:
            log.exception("keepalive: ping failed")
        await asyncio.sleep(interval)
