import asyncio
import json
import re
from dataclasses import dataclass, asdict
from functools import lru_cache
from typing import cast
from urllib.parse import urljoin

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
                'article a[href*="/movie/"], article a[href*="/serie/"]',
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
        link = art.select_one('a[href*="/movie/"], a[href*="/serie/"]')
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
        kind = "series" if "/serie" in href else "movie"
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
