from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models


router = APIRouter()


@router.get('/updates')
async def get_updates(session_id: str, since: str | None = None, db: Session = Depends(get_db)):
    # Topics for the session
    topics = [st.topic_id for st in db.query(models.SessionTopic).filter_by(session_id=session_id).all()]
    # Messages reuse messages API logic
    from datetime import datetime
    q = db.query(models.Message).filter(models.Message.session_id == session_id)
    if since:
        try:
            dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            q = q.filter(models.Message.created_at > dt)
        except Exception:
            raise HTTPException(status_code=400, detail='invalid since')
    q = q.order_by(models.Message.created_at.asc())
    messages = [
        {
            "id": m.id,
            "topic_id": m.topic_id,
            "payload_json": m.payload_json,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in q.all()
    ]
    return {"topics": topics, "messages": messages}


