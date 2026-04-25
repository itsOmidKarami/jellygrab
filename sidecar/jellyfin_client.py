import httpx

from config import settings


class JellyfinClient:
    def __init__(self) -> None:
        self._base = settings.jellyfin_url
        self._headers = {
            "X-Emby-Token": settings.jellyfin_api_key,
            "Accept": "application/json",
        }

    async def search_library(self, term: str) -> list[dict]:
        """Return matching Jellyfin library items for a title."""
        if not settings.jellyfin_api_key or not settings.jellyfin_user_id:
            return []
        async with httpx.AsyncClient(base_url=self._base, headers=self._headers, timeout=15.0) as c:
            resp = await c.get(
                f"/Users/{settings.jellyfin_user_id}/Items",
                params={
                    "searchTerm": term,
                    "IncludeItemTypes": "Movie,Series",
                    "Recursive": "true",
                    "Limit": 10,
                    "Fields": "ProductionYear",
                },
            )
            resp.raise_for_status()
            return resp.json().get("Items", [])

    async def refresh_library(self) -> None:
        """Trigger a full library refresh after a download completes."""
        if not settings.jellyfin_api_key:
            return
        async with httpx.AsyncClient(base_url=self._base, headers=self._headers, timeout=15.0) as c:
            resp = await c.post("/Library/Refresh")
            resp.raise_for_status()


jellyfin = JellyfinClient()
