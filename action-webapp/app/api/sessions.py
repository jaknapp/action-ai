from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class SessionCreate(BaseModel):
    session_id: str
    topic_id: str | None = None

@router.post('/sessions')
async def create_session(payload: SessionCreate):
    # stub: real impl will persist and subscribe queue to topic
    return {session_id: payload.session_id, topic_id: payload.topic_id}

@router.get('/health')
async def health():
    return {ok: True}
