import asyncio
import json
import logging
import re
from dataclasses import dataclass, asdict
from functools import lru_cache
from pathlib import Path
from typing import cast
from urllib.parse import urljoin

log = logging.getLogger("jellynama.scraper")
log.setLevel(logging.INFO)
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(_h)
    log.propagate = False

from playwright.async_api import (
    Browser,
    BrowserContext,
    Playwright,
    async_playwright,
)

from config import settings


@dataclass
class DownloadOption:
    quality: str
    url: str
    size: str | None = None
    resolution: str | None = None
    encoder: str | None = None
    tags: list[str] | None = None
    # Series-only: when this option is a (season, quality) pack, `url` is empty
    # and `episodes` lists each episode's direct .mkv URL. The downloader fans
    # out one job per episode.
    season: str | None = None
    episodes: list[dict] | None = None


@dataclass
class SearchResult:
    title: str
    year: str | None
    poster: str | None
    detail_url: str
    kind: str  # "movie" | "series" | "unknown"

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def _cookie_jar() -> dict[str, str]:
    """Cookies merged from NAMA_COOKIES_FILE (JSON dict) + NAMA_COOKIE (header string)."""
    jar: dict[str, str] = {}
    if settings.nama_cookies_file and settings.nama_cookies_file.exists():
        data = json.loads(settings.nama_cookies_file.read_text())
        jar.update({str(k): str(v) for k, v in data.items()})
    if settings.nama_cookie:
        for part in settings.nama_cookie.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                jar[k] = v
    return jar


def cookie_jar() -> dict[str, str]:
    return dict(_cookie_jar())


async def persist_cookies(ctx: BrowserContext) -> dict[str, str]:
    """Snapshot the context's 30nama cookies back to NAMA_COOKIES_FILE.

    Cloudflare may rotate `cf_clearance` (and the site itself rotates session
    cookies) during normal navigation. Capturing them here means the next
    request resumes with the live values instead of the stale on-disk copy.

    Returns the merged jar that was written.
    """
    target = settings.nama_cookies_file
    if not target:
        return {}
    raw = await ctx.cookies()
    fresh = {
        c["name"]: c["value"]
        for c in raw
        if "30nama.com" in c.get("domain", "")
    }
    if not fresh:
        return {}
    existing: dict[str, str] = {}
    if target.exists():
        try:
            existing = json.loads(target.read_text())
        except Exception:
            existing = {}
    merged = {**existing, **fresh}
    if merged == existing:
        return merged
    # Direct write (not rename-from-tmp): the cookies file is a single-file
    # docker bind-mount and `os.replace` fails with EBUSY across that boundary.
    target.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
    _cookie_jar.cache_clear()
    return merged


# Singleton browser — launched on first use, reused for the process lifetime.
_lock = asyncio.Lock()
_pw: Playwright | None = None
_browser: Browser | None = None


async def startup() -> None:
    global _pw, _browser
    async with _lock:
        if _browser is None:
            _pw = await async_playwright().start()
            _browser = await _pw.chromium.launch(headless=True)


async def shutdown() -> None:
    global _pw, _browser
    async with _lock:
        if _browser is not None:
            await _browser.close()
            _browser = None
        if _pw is not None:
            await _pw.stop()
            _pw = None


async def _new_context() -> BrowserContext:
    if _browser is None:
        await startup()
    browser = cast(Browser, _browser)
    ctx = await browser.new_context(user_agent=settings.nama_user_agent)
    cookies = [
        {"name": k, "value": v, "domain": ".30nama.com", "path": "/"}
        for k, v in cookie_jar().items()
    ]
    if cookies:
        await ctx.add_cookies(cookies)
    return ctx


async def search(query: str) -> list[SearchResult]:
    """Search 30nama.com for the given title via a real Chromium render."""
    url = f"{settings.nama_base_url}/search?q={query}"
    ctx = await _new_context()
    try:
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_selector(
                'article a[href*="/movie/"], article a[href*="/movies/"], article a[href*="/serie/"], article a[href*="/series/"]',
                timeout=15000,
            )
        except Exception:
            return []
        html = await page.content()
        return _parse_search(html, base=settings.nama_base_url)
    finally:
        await ctx.close()


_YEAR_SUFFIX = re.compile(r"\s+(\d{4})\s*$")


def _parse_search(html: str, base: str) -> list[SearchResult]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    results: list[SearchResult] = []
    for art in soup.find_all("article"):
        link = art.select_one('a[href*="/movie/"], a[href*="/movies/"], a[href*="/serie/"], a[href*="/series/"]')
        if not link:
            continue
        href = link.get("href", "")
        title_el = art.select_one("figcaption h5") or art.select_one("h5") or link
        raw = title_el.get_text(" ", strip=True)
        year_match = _YEAR_SUFFIX.search(raw)
        year = year_match.group(1) if year_match else None
        title = _YEAR_SUFFIX.sub("", raw).strip() if year else raw
        img = art.select_one("img.main-cover") or art.select_one("img")
        poster = (img.get("src") or img.get("data-src")) if img else None
        kind = "series" if ("/series/" in href or "/serie/" in href) else "movie"
        results.append(
            SearchResult(
                title=title,
                year=year,
                poster=urljoin(base, poster) if poster else None,
                detail_url=urljoin(base, href),
                kind=kind,
            )
        )
    return results


async def get_download_options(detail_url: str) -> list[DownloadOption]:
    """Render the detail page (download tab) and extract direct links + metadata."""
    if "section=download" not in detail_url:
        sep = "&" if "?" in detail_url else "?"
        detail_url = f"{detail_url}{sep}section=download"
    if "/series/" in detail_url or "/serie/" in detail_url:
        return await _get_series_packs(detail_url)
    ctx = await _new_context()
    try:
        page = await ctx.new_page()
        await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_selector(
                'a[href$=".mkv"], a[href$=".mp4"], a[href*=".mkv?"], a[href*=".mp4?"]',
                timeout=15000,
            )
        except Exception:
            return []
        html = await page.content()
        return _parse_download_options(html)
    finally:
        await ctx.close()


_DEBUG_DIR = Path("/tmp/jellynama-debug")


async def _navigate_through_cf(page, target_url: str) -> None:
    """Visit homepage first, then the target — mimics click-through navigation
    so Cloudflare treats the request as same-session and rarely challenges.

    On direct navigation to a deep URL, CF often issues a JS challenge with
    `__cf_chl_rt_tk=...` that headless Chromium can take 20s+ to clear (and
    sometimes never does). Warming up via the homepage establishes the session
    in a way CF's heuristics accept, so the second navigation lands directly.
    """
    try:
        await page.goto(settings.nama_base_url, wait_until="domcontentloaded", timeout=20000)
        # If we landed on a CF challenge, give its JS a moment to resolve.
        if "__cf_chl_rt_tk" in page.url or "just a moment" in (await page.title()).lower():
            try:
                await page.wait_for_url(
                    lambda u: "__cf_chl_rt_tk" not in u, timeout=15000
                )
            except Exception:
                log.warning("series: homepage warm-up still on CF challenge: %s", page.url)
    except Exception as exc:
        log.warning("series: homepage warm-up failed: %s", exc)
    await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
    if "__cf_chl_rt_tk" in page.url:
        try:
            await page.wait_for_url(
                lambda u: "__cf_chl_rt_tk" not in u, timeout=20000
            )
        except Exception:
            log.warning("series: target still on CF challenge after wait: %s", page.url)


async def _get_series_packs(detail_url: str) -> list[DownloadOption]:
    """Capture the series download API the SPA fires when a quality row is clicked.

    The series detail page renders only metadata in `section.download-bar` rows;
    real .mkv URLs come from `interface.30nama.com/api/v1/action/download/id/<id>`,
    which the SPA fetches on click. We attach a response listener, navigate, click
    the first row to trigger the call, then parse the JSON.
    """
    log.info("series: starting capture for %s", detail_url)
    ctx = await _new_context()
    try:
        page = await ctx.new_page()
        loop = asyncio.get_running_loop()
        captured: asyncio.Future[dict] = loop.create_future()
        api_urls_seen: list[str] = []

        async def handle_response(resp) -> None:
            url = resp.url
            # Log any interface.30nama.com call so we can see if a different
            # endpoint is being used than the one we're filtering on.
            if "interface.30nama.com" in url or "/action/" in url:
                api_urls_seen.append(f"{resp.status} {url}")
                log.info("series: api response %s %s", resp.status, url)
            if captured.done() or "/action/download/id/" not in url:
                return
            try:
                body = await resp.json()
                log.info("series: captured body keys=%s", list(body.keys()) if isinstance(body, dict) else type(body).__name__)
                captured.set_result(body)
            except Exception as exc:
                log.warning("series: failed to parse body from %s: %s", url, exc)
                if not captured.done():
                    captured.set_exception(exc)

        page.on("response", lambda r: asyncio.create_task(handle_response(r)))

        await _navigate_through_cf(page, detail_url)
        log.info("series: landed on %s", page.url)
        try:
            await page.wait_for_selector("section.download-bar", timeout=20000)
        except Exception:
            # If we hit a Cloudflare challenge, persist whatever new cookies the
            # browser solved so the next request inherits them.
            log.warning("series: section.download-bar not found within 20s; final url=%s", page.url)
            await _dump_debug(page, "no-download-bar")
            await persist_cookies(ctx)
            return []
        # Give Vue hydration a moment so the bars become interactive — without
        # this the first click sometimes lands before the SPA wires its handler
        # and the API call is never fired.
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        # Click quality rows in sequence until one of them triggers the API call.
        bars = await page.query_selector_all("section.download-bar")
        log.info("series: found %d download-bar element(s)", len(bars))
        for idx, bar in enumerate(bars[:5]):
            try:
                await bar.click(timeout=3000)
                log.info("series: clicked bar #%d", idx)
            except Exception as exc:
                log.warning("series: click bar #%d failed: %s", idx, exc)
                continue
            try:
                body = await asyncio.wait_for(asyncio.shield(captured), timeout=6.0)
            except asyncio.TimeoutError:
                log.info("series: bar #%d click did not trigger /action/download/id/ within 6s", idx)
                continue
            except Exception as exc:
                log.warning("series: response capture errored: %s", exc)
                return []
            await persist_cookies(ctx)
            options = _parse_series_packs(body)
            log.info("series: parsed %d pack option(s)", len(options))
            if not options:
                await _dump_debug(page, "empty-packs", body=body)
            return options
        log.warning(
            "series: exhausted %d bar(s) without capturing /action/download/id/. api urls seen=%s",
            len(bars[:5]),
            api_urls_seen,
        )
        await _dump_debug(page, "no-api-call")
        return []
    finally:
        await ctx.close()


async def _dump_debug(page, label: str, body: dict | None = None) -> None:
    """Write the page HTML (and optional captured body) to /tmp for offline inspection."""
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        ts = re.sub(r"[^0-9]", "", str(asyncio.get_running_loop().time()))[:10]
        html_path = _DEBUG_DIR / f"series-{label}-{ts}.html"
        html_path.write_text(await page.content())
        log.info("series: dumped page html to %s (url=%s)", html_path, page.url)
        if body is not None:
            (_DEBUG_DIR / f"series-{label}-{ts}.json").write_text(
                json.dumps(body, indent=2, ensure_ascii=False)
            )
    except Exception as exc:
        log.warning("series: debug dump failed: %s", exc)


def _parse_series_packs(body: dict) -> list[DownloadOption]:
    result = (body or {}).get("result") or {}
    packs = result.get("download") or []
    if packs:
        first = packs[0]
        log.info(
            "series: pack[0] keys=%s scalar_sample=%s",
            list(first.keys()),
            {k: v for k, v in first.items() if not isinstance(v, (list, dict))},
        )
    options: list[DownloadOption] = []
    for pack in packs:
        links = pack.get("link") or []
        episodes = [
            {"episode": str(l.get("episode") or ""), "url": l["dl"]}
            for l in links
            if l.get("dl")
        ]
        if not episodes:
            continue
        season = pack.get("season") or pack.get("season_int")
        season_str = str(season) if season is not None else None
        tag_list = [t for t in (pack.get("note"), pack.get("tags")) if t]
        options.append(
            DownloadOption(
                quality=pack.get("quality") or "unknown",
                url="",
                size=pack.get("size"),
                encoder=pack.get("encoder"),
                tags=tag_list or None,
                season=season_str,
                episodes=episodes,
            )
        )
    return options


_FA_LABELS = {
    "کیفیت": "quality",
    "حجم": "size",
    "رزولوشن": "resolution",
    "انکودر": "encoder",
}


def _parse_download_options(html: str) -> list[DownloadOption]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    options: list[DownloadOption] = []
    seen: set[str] = set()
    # Each download row is a `section.download-bar` containing one `.download-info`
    # (metadata + tags) and one direct video link as a sibling.
    rows = soup.select("section.download-bar") or soup.select("section.download-info")
    for row in rows:
        link = row.select_one('a[href$=".mkv"], a[href$=".mp4"], a[href*=".mkv?"], a[href*=".mp4?"]')
        if not link:
            continue
        href = link.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)
        fields = _extract_long_info(row)
        options.append(
            DownloadOption(
                quality=fields.get("quality") or _quality_from_url(href),
                url=href,
                size=fields.get("size"),
                resolution=fields.get("resolution"),
                encoder=fields.get("encoder"),
                tags=_extract_tags(row),
            )
        )
    if not options:
        # Fallback: any direct video link on the page.
        for link in soup.select('a[href$=".mkv"], a[href$=".mp4"]'):
            href = link.get("href", "")
            if href and href not in seen:
                seen.add(href)
                options.append(DownloadOption(quality=_quality_from_url(href), url=href))
    return options


def _extract_long_info(row) -> dict[str, str]:
    """Read label/value pairs from `.long-info-bar > li`, each `<li>` has two `<p>`."""
    out: dict[str, str] = {}
    for li in row.select(".long-info-bar > li"):
        ps = li.find_all("p")
        if len(ps) < 2:
            continue
        label = ps[0].get_text(" ", strip=True).rstrip(":：").strip()
        value = ps[1].get_text(" ", strip=True)
        key = _FA_LABELS.get(label)
        if key and value:
            out[key] = value
    return out


def _extract_tags(row) -> list[str] | None:
    tags: list[str] = []
    for li in row.select(".tag-content ul > li, .tag-content li"):
        text = li.get_text(" ", strip=True)
        if text and text not in tags:
            tags.append(text)
    return tags or None


def _quality_from_url(url: str) -> str:
    for marker in ("2160p", "1080p", "720p", "480p", "BluRay", "WEB-DL", "HDRip", "BrRip"):
        if marker.lower() in url.lower():
            return marker
    return "unknown"
