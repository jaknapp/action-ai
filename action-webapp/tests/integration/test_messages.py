import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_messages_crud():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create a session to associate messages (via API)
        sess = await ac.post('/api/sessions', json={})
        session_id = sess.json()['id']

        # Create messages
        for i in range(3):
            resp = await ac.post('/api/messages', json={
                'session_id': session_id,
                'topic_id': 't1',
                'payload': {'n': i}
            })
            assert resp.status_code == 200

        # List messages
        resp = await ac.get('/api/messages', params={'session_id': session_id})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 3
        assert [i for i in range(3)] == [int(eval(x['payload_json'])['n']) for x in items]


