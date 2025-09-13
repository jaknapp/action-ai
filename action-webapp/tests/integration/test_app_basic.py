from httpx import AsyncClient
from app.main import app
import pytest

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(app=app, base_url='http://test') as ac:
        resp = await ac.get('/api/health')
        assert resp.status_code == 200
        assert resp.json()[ok] is True

@pytest.mark.asyncio
async def test_create_session_stub():
    async with AsyncClient(app=app, base_url='http://test') as ac:
        payload = {session_id: s1, topic_id: t1}
        resp = await ac.post('/api/sessions', json=payload)
        assert resp.status_code == 200
        assert resp.json()[session_id] == s1
