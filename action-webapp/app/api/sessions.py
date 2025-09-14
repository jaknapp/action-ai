from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models
from app.core.config import settings
import httpx

router = APIRouter()

class SessionCreate(BaseModel):
    topic_id: str | None = None


class SessionOut(BaseModel):
    id: str
    class Config:
        from_attributes = True

@router.post('/sessions', response_model=SessionOut)
async def create_session(payload: SessionCreate, db: Session = Depends(get_db)):
    session = models.Session()
    db.add(session)
    db.flush()
    if payload.topic_id:
        db.add(models.SessionTopic(session_id=session.id, topic_id=payload.topic_id))
    db.commit()
    db.refresh(session)
    return session


@router.get('/sessions', response_model=list[SessionOut])
async def list_sessions(db: Session = Depends(get_db)):
    return db.query(models.Session).all()


@router.post('/sessions/{session_id}/topics')
async def add_topic(session_id: str, payload: dict, db: Session = Depends(get_db)):
    topic_id = payload.get('topic_id')
    if not topic_id:
        raise HTTPException(status_code=400, detail='topic_id required')
    exists = db.get(models.Session, session_id)
    if not exists:
        raise HTTPException(status_code=404, detail='session not found')
    db.add(models.SessionTopic(session_id=session_id, topic_id=topic_id))
    db.commit()
    # Best-effort: notify action-terminal to associate topic with session
    try:
        async with httpx.AsyncClient() as client:
            await client.post(f"{settings.ACTION_TERMINAL_URL}/sessions/{session_id}/topics", json={"topic_id": topic_id}, timeout=2.0)
    except Exception:
        pass
    return {"ok": True}


@router.delete('/sessions/{session_id}/topics/{topic_id}')
async def remove_topic(session_id: str, topic_id: str, db: Session = Depends(get_db)):
    db.query(models.SessionTopic).filter_by(session_id=session_id, topic_id=topic_id).delete()
    db.commit()
    return {"ok": True}

@router.get('/health')
async def health():
    return {"ok": True}
