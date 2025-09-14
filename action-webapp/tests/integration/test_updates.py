import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_updates_includes_topics_and_messages():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        sess = await ac.post('/api/sessions', json={})
        session_id = sess.json()['id']
        await ac.post(f'/api/sessions/{session_id}/topics', json={'topic_id': 't1'})
        await ac.post('/api/messages', json={'session_id': session_id, 'topic_id': 't1', 'payload': {'x': 1}})

        resp = await ac.get('/api/updates', params={'session_id': session_id})
        data = resp.json()
        assert 't1' in data['topics']
        assert len(data['messages']) == 1


