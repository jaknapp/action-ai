from typing import Literal

from pydantic import BaseModel

from action.app.action_service_types import (
    ActionServiceExecutionRequestNewProcess,
    ActionServiceExecutionRequestProcess,
    ActionServiceExecutionResponseNewProcess,
    ActionServiceExecutionResponseProcess,
)


class ActionServerResponse(BaseModel):
    error: str | None = None


class ActionServerSession(BaseModel):
    session_id: str


class ActionServerExecutionRequest(BaseModel):
    session: ActionServerSession
    loopback_payload: str | None = None
    new_processes: list[ActionServiceExecutionRequestNewProcess] | None = None
    processes: dict[str, ActionServiceExecutionRequestProcess] | None = None
    # The upper limit in seconds on how long to wait for a response before
    # returning the current results of all processes
    poll_interval: int | None = None


class ActionServerExecutionResponse(BaseModel):
    loopback_payload: str | None = None
    new_processes: list[ActionServiceExecutionResponseNewProcess | None] | None = None
    processes: dict[
        str, ActionServiceExecutionResponseProcess
    ] | None = None  # key is pid
    error: str | None = None


class ActionServerSessionsItem(BaseModel):
    session_id: str


class ActionServerSessionsResponse(BaseModel):
    items: list[ActionServerSessionsItem]
    page: int
    page_size: int
    total: int
    has_next: bool


class ActionServerSnapshotProcessState(BaseModel):
    running_command_id: str | None = None
    is_done_logging_in: bool = False


class ActionServerWebsocketSnapshot(BaseModel):
    type: Literal["snapshot"]
    session_id: str
    execution_ids: list[str]
    processes: dict[str, ActionServerSnapshotProcessState]


class ActionServerAddTopicRequest(BaseModel):
    topic_id: str


class ActionServerStateRequest(BaseModel):
    sessions: list[str]
    topic_id: str | None = None
