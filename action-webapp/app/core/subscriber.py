import asyncio
import json
from typing import AsyncGenerator

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.db import models


async def stream_topic(topic_id: str) -> AsyncGenerator[dict, None]:
    url = f"{settings.ACTION_TERMINAL_URL}/topics/{topic_id}/stream"
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("GET", url) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        yield json.loads(line[6:])
                    except Exception:
                        continue


async def _persist_message(session_id: str, topic_id: str, payload: dict) -> None:
    db: Session = SessionLocal()
    try:
        db.add(models.Message(session_id=session_id, topic_id=topic_id, payload_json=json.dumps(payload)))
        db.commit()
    finally:
        db.close()


async def subscribe_topics_forever() -> None:
    if not settings.ENABLE_TOPIC_SUBSCRIBER:
        return
    while True:
        db: Session = SessionLocal()
        try:
            subs = db.query(models.SessionTopic).all()
            tasks = []
            for st in subs:
                async def run(st_local=st):
                    async for msg in stream_topic(st_local.topic_id):
                        sid = msg.get('session_id') or st_local.session_id
                        await _persist_message(sid, st_local.topic_id, msg)
                tasks.append(asyncio.create_task(run()))
        finally:
            db.close()
        if not tasks:
            await asyncio.sleep(1.0)
            continue
        try:
            await asyncio.gather(*tasks)
        except Exception:
            await asyncio.sleep(1.0)


