import dataclasses

import httpx
import jellyfin_client
import pytest


@pytest.fixture
def client(monkeypatch):
    settings = dataclasses.replace(
        jellyfin_client.settings,
        jellyfin_url="http://jellyfin:8096",
        jellyfin_api_key="abc123",
        jellyfin_user_id="user-1",
    )
    monkeypatch.setattr(jellyfin_client, "settings", settings)
    return jellyfin_client.JellyfinClient()


async def test_requests_use_authorization_header_not_legacy_token(client, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"Items": []})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        jellyfin_client.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    await client.search_library("Heat")
    await client.refresh_library()

    assert len(seen) == 2
    for request in seen:
        assert request.headers["Authorization"] == 'MediaBrowser Token="abc123"'
        assert "x-emby-token" not in request.headers
