from collections import defaultdict
from typing import Awaitable, Callable, DefaultDict, Tuple

from aiohttp import web
import aiohttp_cors

from action.app.action_server_types import (
    ActionServerExecutionRequest,
    ActionServerExecutionResponse,
    ActionServerResponse,
    ActionServerSessionsItem,
    ActionServerSessionsResponse,
    ActionServerWebsocketSnapshot,
)
from action.app.action_service import ActionService, ActionServiceObserver
from action.app.topic_manager import TopicManager
from action.app.action_service_types import (
    ActionServiceExecutionReference,
    ActionServiceExecutionRequest,
    ActionServiceExecutionResponse,
)


class ActionServerExecutionObserver(ActionServiceObserver):
    def __init__(
        self,
        session_id_web_sockets: DefaultDict[str, list[web.WebSocketResponse]],
        execution_id_session_id_dict: dict[str, str],
        topic_manager: TopicManager,
        session_id_topics: DefaultDict[str, set[str]],
    ):
        self._session_id_web_sockets = session_id_web_sockets
        self._execution_id_session_id_dict = execution_id_session_id_dict
        self._topic_manager = topic_manager
        self._session_id_topics = session_id_topics

    async def receive_execution_response(
        self, response: ActionServiceExecutionResponse
    ) -> None:
        if (
            session_id := self._execution_id_session_id_dict.get(response.execution_id)
        ) is None:
            print(
                f"Session not found for {response.execution_id}. Dropping response "
                f"{response}"
            )
            return
        web_sockets = self._session_id_web_sockets[session_id]
        print(
            f"Sending execution ({response.execution_id}) response for session "
            f"{session_id} to {len(web_sockets)} web sockets."
        )
        
        # Create a new list to store active websockets
        active_web_sockets = []
        
        def _coerce_bytes_to_text(obj):
            if isinstance(obj, bytes):
                try:
                    return obj.decode("utf-8", errors="ignore")
                except Exception:
                    return ""
            if isinstance(obj, list):
                return [_coerce_bytes_to_text(x) for x in obj]
            if isinstance(obj, dict):
                return {k: _coerce_bytes_to_text(v) for k, v in obj.items()}
            return obj

        # Build payload once for both websockets and topic publishing
        server_response = ActionServerExecutionResponse(
            loopback_payload=response.loopback_payload,
            new_processes=response.new_processes,
            processes=response.processes,
            error=response.error,
        )
        payload = server_response.model_dump(exclude_defaults=True)
        payload = _coerce_bytes_to_text(payload)

        for web_socket in web_sockets:
            try:
                print(f"Sending response {payload}")
                await web_socket.send_json(payload)
                active_web_sockets.append(web_socket)
            except (ConnectionResetError, ConnectionError) as e:
                print(f"WebSocket connection error: {e}. Removing closed websocket.")
                continue
            except Exception as e:
                print(f"Unexpected error sending to websocket: {e}")
                continue
        
        # Update the list of websockets for this session
        self._session_id_web_sockets[session_id] = active_web_sockets

        # Also publish to all session topics for at-least-once delivery
        topics = self._session_id_topics.get(session_id, set())
        if topics:
            publish_payload = {"session_id": session_id, **payload}
            for topic_id in topics:
                try:
                    await self._topic_manager.publish(topic_id, publish_payload)
                except Exception as e:
                    print(f"Error publishing to topic {topic_id}: {e}")


def _get_request_log_values(
    request: web.Request,
) -> Tuple[str | None, str | None, str | None, str | None, str | None, str | None]:
    websocket_key = request.headers.get("Sec-WebSocket-Key")
    peername = request.transport.get_extra_info("peername")
    host, port = (None, None) if peername is None else peername[:2]
    host = None if host is None else str(host)
    port = None if port is None else str(port)
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    remote = request.remote
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(",")[
            0
        ]  # In case there are multiple addresses
    else:
        client_ip = request.remote
    return client_ip, websocket_key, host, port, remote, x_forwarded_for


def _processes_state_list_to_dict(processes_state: list[dict] | None) -> dict:
    """Convert service get_execution_state processes list to pid-keyed dict.

    Each item is expected to have a 'pid' key. Values exclude the pid field.
    """
    if not processes_state:
        return {}
    result: dict[str, dict] = {}
    for item in processes_state:
        pid = item.get("pid")
        if pid is None:
            # Skip malformed entries
            continue
        # Exclude pid from the nested dict
        result[str(pid)] = {k: v for k, v in item.items() if k != "pid"}
    return result


class ActionServer:
    """Handle web requests and invoke the ActionService"""

    def __init__(self, action_service: ActionService, topic_manager: TopicManager):
        self._action_service = action_service
        self._session_id_web_sockets: DefaultDict[
            str, list[web.WebSocketResponse]
        ] = defaultdict(list)
        self._session_id_executions_dict: DefaultDict[
            str, list[ActionServiceExecutionReference]
        ] = defaultdict(list)
        self._execution_id_session_id_dict: dict[str, str] = {}
        self._session_id_topics: DefaultDict[str, set[str]] = defaultdict(set)
        self._topic_manager = topic_manager
        observer = ActionServerExecutionObserver(
            session_id_web_sockets=self._session_id_web_sockets,
            execution_id_session_id_dict=self._execution_id_session_id_dict,
            topic_manager=self._topic_manager,
            session_id_topics=self._session_id_topics,
        )
        self._action_service.set_observer(observer)
        self._service = action_service

    def _remove_websocket(self, session_id: str, web_socket: web.WebSocketResponse) -> None:
        """Remove a websocket from tracking when it's closed."""
        if session_id in self._session_id_web_sockets:
            self._session_id_web_sockets[session_id] = [
                ws for ws in self._session_id_web_sockets[session_id] 
                if ws is not web_socket
            ]
            if not self._session_id_web_sockets[session_id]:
                del self._session_id_web_sockets[session_id]
            print(f"Removed closed websocket for session {session_id}")

    async def websocket(self, request: web.Request) -> web.WebSocketResponse:
        session_id = request.headers.get("session_id")

        # This is all not strictly necessary but am printing it for curiosity
        request_log_values = _get_request_log_values(request)
        print(f"WebSocket connection starting {request_log_values}")
        if session_id is None:
            server_response = ActionServerResponse(
                error="Missing 'session_id' header in websocket request.",
                status=400,
            )
            return web.json_response(
                server_response.model_dump_json(exclude_defaults=True)
            )
        web_socket = web.WebSocketResponse()
        await web_socket.prepare(request)
        self._session_id_web_sockets[session_id].append(web_socket)

        # Send snapshot immediately only if we have executions for this session
        execution_refs = self._session_id_executions_dict.get(session_id, [])
        if execution_refs:
            execution_ids = [ref.execution_id for ref in execution_refs]
            state = self._action_service.get_execution_state(execution_ids)
            snapshot = ActionServerWebsocketSnapshot(
                type="snapshot",
                session_id=session_id,
                execution_ids=execution_ids,
                processes=_processes_state_list_to_dict(state.get("processes")),
            )
            await web_socket.send_json(snapshot.model_dump(exclude_defaults=True))

        # # Set up a task to monitor the websocket closure
        # async def monitor_websocket():
        #     try:
        #         await web_socket.wait_closed()
        #         self._remove_websocket(session_id, web_socket)
        #     except Exception as e:
        #         print(f"Error monitoring websocket closure: {e}")
        #         self._remove_websocket(session_id, web_socket)

        # asyncio.create_task(monitor_websocket())

        async for message in web_socket:
            if message.type == web.WSMsgType.TEXT:
                print(f"Unexpected message: {message.data}")
            elif message.type == web.WSMsgType.ERROR:
                print(
                    "WebSocket connection closed with exception:",
                    web_socket.exception(),
                )
                self._remove_websocket(session_id, web_socket)

        print(f"WebSocket connection closed {request_log_values}")
        return web_socket

    async def execute(self, request: web.Request) -> web.Response:
        request_log_values = _get_request_log_values(request)
        print(f"Execute POST request for {request_log_values}")
        print(await request.json())
        server_request = ActionServerExecutionRequest(**await request.json())
        print(server_request.model_dump_json(exclude_defaults=True))
        service_request = ActionServiceExecutionRequest(
            loopback_payload=server_request.loopback_payload,
            new_processes=server_request.new_processes,
            processes=server_request.processes,
            poll_interval=server_request.poll_interval,
        )
        session_id = server_request.session.session_id
        # Update poll interval for all executions in this session
        if server_request.poll_interval is not None:
            session_executions = self._session_id_executions_dict.get(session_id, [])
            for session_execution in session_executions:
                self._action_service.set_poll_interval(
                    reference=session_execution,
                    poll_interval=server_request.poll_interval,
                )
        # Start a new execution
        execution_reference = self._action_service.execute(service_request)
        self._session_id_executions_dict[session_id].append(execution_reference)
        self._execution_id_session_id_dict[
            execution_reference.execution_id
        ] = session_id
        print(
            f"Execution reference {execution_reference.execution_id} for session "
            f"{session_id}"
        )
        server_response = ActionServerResponse()
        return web.json_response(server_response.model_dump_json(exclude_defaults=True))

    def shutdown(self) -> None:
        self._action_service.shutdown()


    async def sessions(self, request: web.Request) -> web.Response:
        """Return paginated list of available sessions.

        Query params:
          - page: 1-based page index (default 1)
          - page_size: number of items per page (default 50, max 1000)
        """
        # Parse pagination params
        try:
            page = int(request.query.get("page", "1"))
            page_size = int(request.query.get("page_size", "50"))
        except ValueError:
            return web.json_response({"error": "invalid pagination params"}, status=400)

        if page < 1 or page_size < 1 or page_size > 1000:
            return web.json_response({"error": "invalid pagination params"}, status=400)

        # Combine sessions known via websocket and executions
        session_ids = sorted(
            set(self._session_id_executions_dict.keys())
            | set(self._session_id_web_sockets.keys())
        )
        total = len(session_ids)
        start = (page - 1) * page_size
        end = start + page_size

        if start >= total and total != 0:
            return web.json_response({"error": "page out of range"}, status=400)

        page_items = [ActionServerSessionsItem(session_id=sid) for sid in session_ids[start:end]]

        response = ActionServerSessionsResponse(
            items=page_items,
            page=page,
            page_size=page_size,
            total=total,
            has_next=end < total,
        )
        return web.json_response(response.model_dump(exclude_defaults=True))

    async def add_topic(self, request: web.Request) -> web.Response:
        session_id = request.match_info.get("session_id")
        try:
            body = await request.json()
        except Exception:
            body = {}
        topic_id = body.get("topic_id")
        if not session_id or not topic_id:
            return web.json_response({"error": "missing session_id or topic_id"}, status=400)
        self._session_id_topics[session_id].add(topic_id)
        return web.json_response({"ok": True})

    async def remove_topic(self, request: web.Request) -> web.Response:
        session_id = request.match_info.get("session_id")
        topic_id = request.match_info.get("topic_id")
        if not session_id or not topic_id:
            return web.json_response({"error": "missing session_id or topic_id"}, status=400)
        if session_id in self._session_id_topics:
            self._session_id_topics[session_id].discard(topic_id)
            if not self._session_id_topics[session_id]:
                del self._session_id_topics[session_id]
        return web.json_response({"ok": True})

    async def delete_session(self, request: web.Request) -> web.Response:
        session_id = request.match_info.get("session_id")
        if not session_id:
            return web.json_response({"error": "missing session_id"}, status=400)
        self._session_id_web_sockets.pop(session_id, None)
        self._session_id_executions_dict.pop(session_id, None)
        self._session_id_topics.pop(session_id, None)
        # Remove any execution_id -> session mapping entries for this session
        to_delete = [eid for eid, sid in self._execution_id_session_id_dict.items() if sid == session_id]
        for eid in to_delete:
            del self._execution_id_session_id_dict[eid]
        return web.json_response({"ok": True})

    async def state(self, request: web.Request) -> web.Response:
        """Request current state for sessions; publish via websockets and/or topics.

        Body: {"sessions": ["session-1", ...], "topic_id": "optional"}
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        sessions = body.get("sessions") or []
        explicit_topic = body.get("topic_id")
        if not isinstance(sessions, list) or not all(isinstance(s, str) for s in sessions):
            return web.json_response({"error": "sessions must be a list of strings"}, status=400)

        for session_id in sessions:
            execution_refs = self._session_id_executions_dict.get(session_id, [])
            execution_ids = [ref.execution_id for ref in execution_refs]
            state = self._action_service.get_execution_state(execution_ids)
            snapshot = ActionServerWebsocketSnapshot(
                type="snapshot",
                session_id=session_id,
                execution_ids=execution_ids,
                processes=_processes_state_list_to_dict(state.get("processes")),
            )
            payload = snapshot.model_dump(exclude_defaults=True)
            # Send to websockets for the session
            for ws in list(self._session_id_web_sockets.get(session_id, [])):
                try:
                    await ws.send_json(payload)
                except Exception:
                    # Best-effort
                    pass
            # Publish to topic(s)
            topics = set()
            if explicit_topic:
                topics.add(explicit_topic)
            topics |= set(self._session_id_topics.get(session_id, set()))
            for topic_id in topics:
                try:
                    await self._topic_manager.publish(topic_id, payload)
                except Exception as e:
                    print(f"Error publishing snapshot to topic {topic_id}: {e}")
        return web.json_response({"ok": True})

class ActionServerRouteHandler:
    def __init__(self, instance_app_key: web.AppKey):
        self._instance_app_key = instance_app_key

    async def websocket(self, request: web.Request) -> web.WebSocketResponse:
        return await request.app[self._instance_app_key].websocket(request)

    async def execute(self, request: web.Request) -> web.Response:
        return await request.app[self._instance_app_key].execute(request)

    async def sessions(self, request: web.Request) -> web.Response:
        return await request.app[self._instance_app_key].sessions(request)

    async def add_topic(self, request: web.Request) -> web.Response:
        return await request.app[self._instance_app_key].add_topic(request)

    async def remove_topic(self, request: web.Request) -> web.Response:
        return await request.app[self._instance_app_key].remove_topic(request)

    async def delete_session(self, request: web.Request) -> web.Response:
        return await request.app[self._instance_app_key].delete_session(request)

    async def state(self, request: web.Request) -> web.Response:
        return await request.app[self._instance_app_key].state(request)


@web.middleware
async def _error_middleware(
    request: web.Request, handler: Callable[[web.Request], Awaitable[web.Response]]
) -> web.Response:
    import traceback

    try:
        response = await handler(request)
        return response
    except Exception as ex:
        print(traceback.format_exc())
        print("Server Error:", str(ex))
        return web.json_response(
            {"error": "Internal Server Error", "detail": str(ex)}, status=500
        )


def make_action_server_web_app(action_server: ActionServer) -> web.Application:
    app = web.Application(middlewares=[_error_middleware])
    # Callable[["Request"], Awaitable["StreamResponse"]]
    instance_app_key = web.AppKey("instance")
    route_handler = ActionServerRouteHandler(instance_app_key)
    app.add_routes(
        [
            web.get("/websocket", route_handler.websocket),
            web.post("/execute", route_handler.execute),
            web.get("/sessions", route_handler.sessions),
            web.post("/sessions/{session_id}/topics", route_handler.add_topic),
            web.delete("/sessions/{session_id}/topics/{topic_id}", route_handler.remove_topic),
            web.delete("/sessions/{session_id}", route_handler.delete_session),
            web.get("/topics/{topic_id}/stream", lambda r: r.app[instance_app_key]._topic_manager.stream_endpoint(r)),
            web.post("/state", route_handler.state),
        ]
    )
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        )
    })

    # Apply CORS to existing routes and handle all methods including OPTIONS
    for route in list(app.router.routes()):
        cors.add(route)

    app[instance_app_key] = action_server
    return app
