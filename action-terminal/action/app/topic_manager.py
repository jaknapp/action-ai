import asyncio
import json
from collections import defaultdict
from typing import DefaultDict

from aiohttp import web


class TopicSubscriber:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict] = asyncio.Queue()
        self.closed: bool = False

    async def publish(self, message: dict) -> None:
        if self.closed:
            return
        await self.queue.put(message)

    async def close(self) -> None:
        self.closed = True
        await self.queue.put({"__event__": "__closed__"})


class TopicManager:
    """In-memory pub/sub topic manager.

    - Topics are arbitrary strings decided by clients.
    - At-least-once delivery best-effort to all active subscribers.
    - No durability; buffers live in-memory per subscriber.
    """

    def __init__(self) -> None:
        self._topic_subscribers: DefaultDict[str, set[TopicSubscriber]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, topic_id: str, message: dict) -> None:
        # Copy set under lock to avoid holding lock across awaits
        async with self._lock:
            subscribers = list(self._topic_subscribers.get(topic_id, set()))
        # Fan out without ordering guarantees between subscribers
        publish_tasks = [subscriber.publish(message) for subscriber in subscribers]
        if publish_tasks:
            await asyncio.gather(*publish_tasks, return_exceptions=True)

    async def add_subscription(self, topic_id: str) -> TopicSubscriber:
        subscriber = TopicSubscriber()
        async with self._lock:
            self._topic_subscribers[topic_id].add(subscriber)
        return subscriber

    async def remove_subscription(self, topic_id: str, subscriber: TopicSubscriber) -> None:
        async with self._lock:
            subscribers = self._topic_subscribers.get(topic_id)
            if subscribers is None:
                return
            subscribers.discard(subscriber)
            if not subscribers:
                # Optionally delete empty topic mapping
                del self._topic_subscribers[topic_id]

    async def stream_endpoint(self, request: web.Request) -> web.StreamResponse:
        """SSE stream for a topic.

        Route: GET /topics/{topic_id}/stream
        Content-Type: text/event-stream
        Sends each message as a single SSE data event.
        """
        topic_id = request.match_info.get("topic_id")
        if not topic_id:
            return web.json_response({"error": "missing topic_id"}, status=400)

        subscriber = await self.add_subscription(topic_id)

        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await response.prepare(request)

        async def pump() -> None:
            try:
                while True:
                    message = await subscriber.queue.get()
                    # shutdown signal
                    if message.get("__event__") == "__closed__":
                        break
                    payload = json.dumps(message, ensure_ascii=False)
                    data = f"data: {payload}\n\n".encode("utf-8")
                    await response.write(data)
            except (ConnectionResetError, asyncio.CancelledError):
                pass
            finally:
                try:
                    await subscriber.close()
                finally:
                    await self.remove_subscription(topic_id, subscriber)
                with contextlib.suppress(Exception):
                    await response.write_eof()

        # Keep-alive ping task to help proxies
        async def ping() -> None:
            try:
                while True:
                    await asyncio.sleep(15)
                    await response.write(b": keep-alive\n\n")
            except Exception:
                pass

        import contextlib
        pump_task = asyncio.create_task(pump())
        ping_task = asyncio.create_task(ping())
        try:
            await pump_task
        finally:
            ping_task.cancel()
            with contextlib.suppress(Exception):
                await subscriber.close()
            await self.remove_subscription(topic_id, subscriber)
        return response


