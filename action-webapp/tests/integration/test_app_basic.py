from httpx import AsyncClient, ASGITransport
from app.main import app
import pytest


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_create_session_stub():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"topic_id": "t1"}
        resp = await ac.post("/api/sessions", json=payload)
        assert resp.status_code == 200
        assert "id" in resp.json()
