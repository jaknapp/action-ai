from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://action:action@localhost:5432/action"
    ACTION_TERMINAL_URL: str = "http://localhost:5001"
    ENABLE_TOPIC_SUBSCRIBER: bool = True


settings = Settings()

from pydantic import BaseModel
from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    DATABASE_URL: str = 'postgresql+psycopg2://action:action@localhost:5432/action'
settings = Settings()
