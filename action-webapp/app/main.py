from fastapi import FastAPI
import asyncio
from app.api import sessions
from app.api import messages
from app.api import updates
from app.core.subscriber import subscribe_topics_forever

app = FastAPI()
app.include_router(sessions.router, prefix='/api')
app.include_router(messages.router, prefix='/api')
app.include_router(updates.router, prefix='/api')

@app.on_event('startup')
async def _startup():
  asyncio.create_task(subscribe_topics_forever())
