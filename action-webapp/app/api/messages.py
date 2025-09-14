from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json

from app.db.session import get_db
from app.db import models


router = APIRouter()


class MessageIn(BaseModel):
    session_id: str
    topic_id: str
    payload: dict


@router.post('/messages')
async def create_message(message: MessageIn, db: Session = Depends(get_db)):
    payload_json = json.dumps(message.payload)
    db.add(models.Message(session_id=message.session_id, topic_id=message.topic_id, payload_json=payload_json))
    db.commit()
    return {"ok": True}


@router.get('/messages')
async def list_messages(session_id: str, since: str | None = None, db: Session = Depends(get_db)):
    q = db.query(models.Message).filter(models.Message.session_id == session_id)
    if since:
        # Expect ISO8601 timestamp
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            q = q.filter(models.Message.created_at > dt)
        except Exception:
            raise HTTPException(status_code=400, detail='invalid since')
    q = q.order_by(models.Message.created_at.asc())
    return [
        {
            "id": m.id,
            "session_id": m.session_id,
            "topic_id": m.topic_id,
            "payload_json": m.payload_json,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in q.all()
    ]


