from pydantic import BaseModel


class TerminalOutput(BaseModel):
    is_done: bool
    output: bytes | None
    error: str | None
    stop_mark_found: bool = False
