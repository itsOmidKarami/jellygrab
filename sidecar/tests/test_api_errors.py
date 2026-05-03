from fastapi.testclient import TestClient

import keepalive
from main import app


def test_keepalive_run_does_not_expose_exception_details(monkeypatch):
    async def fail_ping():
        raise RuntimeError("secret backend path: /media/downloads/private")

    monkeypatch.setattr(keepalive, "_ping_once", fail_ping)

    with TestClient(app) as client:
        resp = client.post("/api/keepalive/run")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"] == "keepalive check failed"
    assert "secret backend path" not in str(body)
