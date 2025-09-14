from fastapi import FastAPI
from app.api import sessions
from app.api import messages

app = FastAPI()
app.include_router(sessions.router, prefix='/api')
app.include_router(messages.router, prefix='/api')
