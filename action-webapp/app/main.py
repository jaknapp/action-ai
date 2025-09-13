from fastapi import FastAPI
from app.api import sessions

app = FastAPI()
app.include_router(sessions.router, prefix='/api')
