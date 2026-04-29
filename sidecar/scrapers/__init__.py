"""Scraper plugin point.

A scraper is a module that exposes async functions for searching a media
source and resolving download options. The bundled `nama` scraper (for
30nama.com) is the reference implementation. Additional scrapers can be
added under `sidecar/scrapers/<name>/` following the same shape.
"""

from typing import Any, Protocol


class Scraper(Protocol):
    """Shape every scraper module is expected to expose.

    The protocol is structural — a scraper just needs callables with these
    names. Scrapers are imported as modules; the `self` parameter below is
    a notation artifact of `typing.Protocol` and should be ignored when
    implementing — write module-level `async def` functions.
    See `scrapers/nama/scraper.py` for the reference implementation.
    """

    async def startup(self) -> None: ...

    async def shutdown(self) -> None: ...

    async def search(self, query: str) -> list[Any]: ...

    async def get_download_options(self, detail_url: str) -> list[Any]: ...
