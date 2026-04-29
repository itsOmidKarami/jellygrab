"""30nama scraping. All network calls go through FlareSolverr.

We don't run a browser in this process anymore — FlareSolverr does that for us,
solves Cloudflare, and gives us back rendered HTML or JSON. After every
successful call we sync the freshly minted cookies + UA into our local jar so
the curl_cffi downloader can keep using them for the actual `.mkv` fetch.
"""

import asyncio
import json
import logging
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

log = logging.getLogger("jellygrab.scraper")
log.setLevel(logging.INFO)
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(_h)
    log.propagate = False

from curl_cffi.requests import AsyncSession

from . import flaresolverr as fs
from . import session as nama_session
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


# ---- cookie jar (still the source of truth for the downloader) -------------

@lru_cache(maxsize=1)
def _cookie_jar() -> dict[str, str]:
    """Cookies merged from NAMA_COOKIES_FILE (JSON dict) + NAMA_COOKIE (header string)."""
    jar: dict[str, str] = {}
    if settings.nama_cookies_file and settings.nama_cookies_file.exists():
        try:
            data = json.loads(settings.nama_cookies_file.read_text())
            jar.update({str(k): str(v) for k, v in data.items()})
        except Exception:
            pass
    if settings.nama_cookie:
        for part in settings.nama_cookie.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                jar[k] = v
    return jar


def cookie_jar() -> dict[str, str]:
    return dict(_cookie_jar())


# ---- FS plumbing -----------------------------------------------------------

async def _fetch(url: str, *, retry_on_stale: bool = True) -> dict[str, Any]:
    """GET a URL through FlareSolverr and persist the resulting session.

    On a 4xx/5xx response we optionally reset the FS session once and retry —
    this covers the case where FS's cached clearance has gone stale and a fresh
    solve is needed.
    """
    return await _do_request("get", url, retry_on_stale=retry_on_stale)


async def _fetch_post(url: str, post_data: str = "", *, retry_on_stale: bool = True) -> dict[str, Any]:
    """POST a URL through FlareSolverr — needed for SPA action endpoints that
    reject GET (e.g. interface.30nama.com /action/download/id/<id>)."""
    return await _do_request("post", url, post_data=post_data, retry_on_stale=retry_on_stale)


# SPA-baked headers required by interface.30nama.com. The API key is static
# in the deployed bundle; if 30nama rotates it we'd need to refresh this value.
_INTERFACE_API_KEY = "YygufGCvFgYR3g9sjD92Ct5ZSx7SJs4JXpuCeTS24nWAszaL4u3qCDZRULpejmzF"
_INTERFACE_APP_VERSION = "2.0.0"
_INTERFACE_PLATFORM = "Website"


def _interface_user_token() -> str:
    """Extract `usertoken` from the `clientSession` cookie — the SPA reads it
    out and sends it as the `c-token` header on every API call."""
    raw = cookie_jar().get("clientSession")
    if not raw:
        return ""
    from urllib.parse import unquote
    try:
        data = json.loads(unquote(raw))
        return str(data.get("usertoken") or "")
    except Exception:
        return ""


async def _action_post(url: str, form: dict[str, str] | None = None) -> tuple[int, str]:
    """POST to interface.30nama.com /action/* directly via curl_cffi.

    The API rejects requests without the SPA's custom `c-*` headers (api key,
    app version, platform, user token). FlareSolverr can't set those, so we
    send the request ourselves, replaying FS's cookies and UA. curl_cffi's
    chrome impersonation handles the TLS fingerprint.
    """
    ua = nama_session.get_user_agent()
    headers = {
        "User-Agent": ua,
        "Origin": settings.nama_base_url,
        "Referer": settings.nama_base_url + "/",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded",
        "c-api-key": _INTERFACE_API_KEY,
        "c-app-version": _INTERFACE_APP_VERSION,
        "c-platform": _INTERFACE_PLATFORM,
        "c-useragent": ua,
        "c-token": _interface_user_token(),
    }
    async with AsyncSession(impersonate="chrome124") as sess:
        resp = await sess.post(
            url,
            headers=headers,
            cookies=cookie_jar(),
            data=form or "",
            timeout=30,
            allow_redirects=True,
        )
        return resp.status_code, resp.text


async def _ensure_interface_session() -> None:
    """The browser POSTs /action/user before any other action call; without
    that warmup the download endpoint returns 404. We mirror that handshake
    once per FS session."""
    global _user_warmed
    if _user_warmed:
        return
    log.info("interface: warming up via POST %s", _USER_API)
    status, body = await _action_post(_USER_API)
    log.info("interface: /action/user warmup status=%s body_len=%d", status, len(body))
    if status >= 400:
        log.warning("interface: /action/user warmup failed status=%s — resetting FS session and retrying", status)
        await fs.reset_session()
        status, body = await _action_post(_USER_API)
        log.info("interface: /action/user warmup retry status=%s body_len=%d", status, len(body))
    _user_warmed = True


async def _do_request(method: str, url: str, *, post_data: str = "", retry_on_stale: bool = True) -> dict[str, Any]:
    if method == "post":
        sol = await fs.request_post(url, post_data)
    else:
        sol = await fs.request_get(url)
    _absorb(sol)
    status = int(sol.get("status") or 0)
    if status >= 400 and retry_on_stale:
        log.warning("scraper: %s %s returned status=%s; resetting FS session and retrying", method.upper(), url, status)
        global _user_warmed
        _user_warmed = False
        await fs.reset_session()
        if method == "post":
            sol = await fs.request_post(url, post_data)
        else:
            sol = await fs.request_get(url)
        _absorb(sol)
    return sol


def _absorb(sol: dict[str, Any]) -> None:
    """Sync FS-minted cookies + UA into our on-disk session state."""
    fresh = fs.cookies_to_jar(sol.get("cookies") or [])
    if fresh:
        nama_session.merge_cookies(fresh)
        _cookie_jar.cache_clear()
    ua = (sol.get("userAgent") or "").strip()
    if ua:
        nama_session.set_user_agent(ua)


# Compatibility shims — keepalive and main still call these by name.

async def startup() -> None:
    """No-op kept for the lifespan handler."""
    return None


async def shutdown() -> None:
    return None


async def reseed_cookies() -> None:
    """Called after the user pastes new cookies via /api/cookies. We just clear
    our jar cache so the next request reads the fresh on-disk values; FS keeps
    its own session and will re-solve as needed."""
    _cookie_jar.cache_clear()


# ---- search ---------------------------------------------------------------

_SEARCH_API = "https://interface.30nama.com/api/v1/action/search/page/1/order/desc/orderby/favorite/"


async def search(query: str) -> list[SearchResult]:
    """Search via the same JSON API the /explore page uses — POST form data
    `query=<q>`. Scraping the SPA shell isn't viable because results are
    JS-hydrated and FS doesn't wait for hydration."""
    await _ensure_interface_session()
    log.info("search: POSTing %s query=%r", _SEARCH_API, query)
    status, body_text = await _action_post(_SEARCH_API, form={"query": query})
    log.info("search: status=%s body_len=%d", status, len(body_text))
    body = _parse_fs_json(body_text)
    if not body:
        log.warning("search: response did not parse as JSON — dumping")
        _dump_debug(body_text, "search-bad-json")
        return []
    return _parse_search_api(body)


_TITLE_YEAR = re.compile(r"\s+(\d{4})\s*$")


def _parse_search_api(body: dict) -> list[SearchResult]:
    posts = (((body or {}).get("result") or {}).get("posts")) or []
    if not posts:
        log.warning("search: result.posts empty or missing")
        _dump_debug(json.dumps(body, indent=2, ensure_ascii=False), "search-shape")
        return []
    results: list[SearchResult] = []
    for p in posts:
        item_id = p.get("id")
        if not item_id:
            continue
        kind = "series" if (p.get("is_series") or p.get("title_type") == "series") else "movie"
        raw_title = str(p.get("title") or p.get("persian_title") or f"#{item_id}").strip()
        m = _TITLE_YEAR.search(raw_title)
        year = m.group(1) if m else None
        title = _TITLE_YEAR.sub("", raw_title).strip() if year else raw_title
        image = p.get("image") or {}
        poster = None
        if isinstance(image, dict):
            poster_obj = image.get("poster") or {}
            if isinstance(poster_obj, dict):
                poster = poster_obj.get("medium") or poster_obj.get("small") or poster_obj.get("large")
            poster = poster or image.get("cover")
        # Detail URL: /movie/<id>/<slug> or /series/<id>/<slug>. The id alone is
        # enough for our scraping calls; the slug is just for URL aesthetics.
        slug = re.sub(r"[^A-Za-z0-9]+", "-", raw_title).strip("-") or str(item_id)
        detail_url = f"{settings.nama_base_url}/{kind}/{item_id}/{slug}"
        results.append(
            SearchResult(
                title=title,
                year=year,
                poster=str(poster) if poster else None,
                detail_url=detail_url,
                kind=kind,
            )
        )
    log.info("search: parsed %d result(s)", len(results))
    return results


# ---- movie download options ------------------------------------------------

async def get_download_options(detail_url: str) -> list[DownloadOption]:
    if "section=download" not in detail_url:
        sep = "&" if "?" in detail_url else "?"
        detail_url = f"{detail_url}{sep}section=download"
    if "/series/" in detail_url or "/serie/" in detail_url:
        return await _get_series_packs(detail_url)
    return await _get_movie_options(detail_url)


# ---- series packs (HTML + interface API, both via FS) ----------------------

_DEBUG_DIR = Path("/tmp/jellygrab-debug")
_DOWNLOAD_API = "https://interface.30nama.com/api/v1/action/download/id/{id}"
_USER_API = "https://interface.30nama.com/api/v1/action/user"
# Avoid POSTing /action/user on every call — once per process is enough as long
# as the FS session is alive. We re-warm it after a session reset.
_user_warmed = False
# Item id appears in the URL path: /movie/6276/Iron-Man-2008 or /series/12345/slug.
_ID_FROM_URL = re.compile(r"/(?:movie|series|serie|movies)/(\d+)(?:/|$|\?)")


async def _get_series_packs(detail_url: str) -> list[DownloadOption]:
    log.info("series: starting capture for %s", detail_url)
    # 1. Pull the detail HTML so we have something to extract the series id from.
    sol = await _fetch(detail_url)
    html = sol.get("response") or ""
    series_id = _extract_item_id(detail_url, html)
    if not series_id:
        log.warning("series: could not extract series id from %s — dumping page", detail_url)
        _dump_debug(html, "no-series-id")
        return []
    # 2. Hit the SPA's download API directly. FS happily fetches JSON URLs and
    # returns the body as `response`. We strip <html><body><pre>...</pre>... if
    # FS wraps it (it sometimes does for non-HTML responses).
    await _ensure_interface_session()
    api_url = _DOWNLOAD_API.format(id=series_id)
    log.info("series: POSTing %s", api_url)
    status, body_text = await _action_post(api_url)
    log.info("series: /action/download status=%s body_len=%d", status, len(body_text))
    body = _parse_fs_json(body_text)
    if not body:
        log.warning("series: API response did not parse as JSON — dumping")
        _dump_debug(body_text, "bad-api-json")
        return []
    options = _parse_series_packs(body)
    log.info("series: parsed %d pack option(s) for id=%s", len(options), series_id)
    if not options:
        _dump_debug(json.dumps(body, indent=2, ensure_ascii=False), "empty-packs")
    return options


async def _get_movie_options(detail_url: str) -> list[DownloadOption]:
    """Movie download list is hydrated client-side from the same /action/download/id/<id>
    endpoint that series uses. Skip the SPA shell entirely and hit the API."""
    log.info("movie: starting capture for %s", detail_url)
    movie_id = _extract_item_id_from_url(detail_url)
    if not movie_id:
        # The id is normally in the URL; only fall back to fetching+scraping HTML if it isn't.
        sol = await _fetch(detail_url)
        movie_id = _extract_item_id(detail_url, sol.get("response") or "")
    if not movie_id:
        log.warning("movie: could not extract movie id from %s", detail_url)
        return []
    await _ensure_interface_session()
    api_url = _DOWNLOAD_API.format(id=movie_id)
    log.info("movie: POSTing %s", api_url)
    status, body_text = await _action_post(api_url)
    log.info("movie: /action/download status=%s body_len=%d", status, len(body_text))
    body = _parse_fs_json(body_text)
    if not body:
        log.warning("movie: API response did not parse as JSON — dumping")
        _dump_debug(body_text, "movie-bad-api-json")
        return []
    options = _parse_movie_options_api(body)
    log.info("movie: parsed %d option(s) for id=%s", len(options), movie_id)
    if not options:
        _dump_debug(json.dumps(body, indent=2, ensure_ascii=False), "movie-empty-api")
    return options


def _extract_item_id_from_url(detail_url: str) -> str | None:
    m = _ID_FROM_URL.search(detail_url)
    return m.group(1) if m else None


def _parse_movie_options_api(body: dict) -> list[DownloadOption]:
    """Parse the movie variant of `/action/download/id/<id>`.

    Shape isn't documented; we accept either a flat list of qualities at
    `result.download[]` (each with a single `dl` URL) or the same `link[]`
    array shape series uses (in which case we take the first entry).
    """
    result = (body or {}).get("result") or {}
    items = result.get("download") or []
    if items:
        first = items[0]
        log.info(
            "movie: pack[0] keys=%s scalar_sample=%s",
            list(first.keys()),
            {k: v for k, v in first.items() if not isinstance(v, (list, dict))},
        )
    options: list[DownloadOption] = []
    for item in items:
        url = item.get("dl") or item.get("url") or item.get("link_url") or ""
        if not url:
            links = item.get("link") or []
            if links and isinstance(links, list) and isinstance(links[0], dict):
                url = links[0].get("dl") or links[0].get("url") or ""
        if not url:
            continue
        tag_list = [t for t in (item.get("note"), item.get("tags")) if t]
        options.append(
            DownloadOption(
                quality=item.get("quality") or _quality_from_url(url),
                url=url,
                size=item.get("size"),
                resolution=item.get("resolution"),
                encoder=item.get("encoder"),
                tags=tag_list or None,
            )
        )
    return options


def _extract_item_id(detail_url: str, html: str) -> str | None:
    """Try multiple strategies — URL first (most reliable), then HTML scrape."""
    m = _ID_FROM_URL.search(detail_url)
    if m:
        return m.group(1)
    m = re.search(r'data-(?:movie-|series-)?id\s*=\s*"(\d+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'"(?:movie|series)[_-]?id"\s*:\s*"?(\d+)"?', html, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'/(?:movie|series)/(\d+)(?:/|")', html)
    if m:
        return m.group(1)
    return None


def _parse_fs_json(body_text: str) -> dict | None:
    """FS returns response bodies wrapped in <html><head></head><body><pre>...</pre>...
    when the upstream content-type isn't HTML. Strip that envelope before parsing."""
    text = (body_text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"<pre[^>]*>(.*?)</pre>", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            return None
    return None


def _dump_debug(content: str, label: str) -> None:
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        import time as _time
        ts = str(_time.monotonic_ns())[-10:]
        path = _DEBUG_DIR / f"series-{label}-{ts}.html"
        path.write_text(content)
        log.info("series: dumped to %s", path)
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


def _quality_from_url(url: str) -> str:
    for marker in ("2160p", "1080p", "720p", "480p", "BluRay", "WEB-DL", "HDRip", "BrRip"):
        if marker.lower() in url.lower():
            return marker
    return "unknown"
