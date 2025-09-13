import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.db.session as session_mod


@pytest.fixture(autouse=True)
def sqlite_db(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path}/test.db"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TestingSessionLocal)
    yield
    Base.metadata.drop_all(bind=engine)


