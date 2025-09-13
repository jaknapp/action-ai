import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.base import Base
from app.db.session import SessionLocal


@pytest.fixture(autouse=True)
def _override_db(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path}/test.db"
    engine = create_engine(url)
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr('app.db.session.SessionLocal', TestingSessionLocal)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_sessions_crud_and_topics():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create session without topic
        resp = await ac.post('/api/sessions', json={})
        assert resp.status_code == 200
        session_id = resp.json()['id']

        # List sessions
        resp = await ac.get('/api/sessions')
        assert resp.status_code == 200
        assert any(item['id'] == session_id for item in resp.json())

        # Add topic
        resp = await ac.post(f'/api/sessions/{session_id}/topics', json={'topic_id': 't1'})
        assert resp.status_code == 200

        # Remove topic
        resp = await ac.delete(f'/api/sessions/{session_id}/topics/t1')
        assert resp.status_code == 200


