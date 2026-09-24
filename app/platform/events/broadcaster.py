import asyncio
import json
import threading
from collections.abc import AsyncIterator
from typing import Any

from app.db.base import utcnow

HEARTBEAT_SECONDS = 15.0
HEARTBEAT_FRAME = ": keep-alive\n\n"
CONNECTED_FRAME =": connected\n\n"


def make_event(event_type: str, event_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Every stream message has the same four keys: {type, id, data, at}"""
    return {
        "type": event_type,
        "id": event_id,
        "data": data,
        "at": utcnow().isoformat(),
    }


def format_sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


class Broadcaster:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}

    def subscribe(self, topic: str) -> asyncio.Queue:
        """Must be called from inside the event loop that will read the queue"""
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscribers.setdefault(topic, []).append((loop, queue))
        return queue

    def unsubscribe(self, topic: str, queue: asyncio.Queue) -> None:
        with self._lock:
            remaining = [pair for pair in self._subscribers.get(topic, []) if pair[1] is not queue]
            if remaining:
                self._subscribers[topic] = remaining
            else:
                self._subscribers.pop(topic, None)

    def publish(self, topic: str, event: dict[str, Any]) -> None:
        with self._lock:
            targets = list(self._subscribers.get(topic, []))
        for loop, queue in targets:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:
                pass # event loop is closed, ignore


    def subscribe_count(self, topic: str) -> int:
        with self._lock:
            return len(self._subscribers.get(topic, []))

    async def event_stream(
            self, topic: str, heartbeat_seconds: float = HEARTBEAT_SECONDS
    ) -> AsyncIterator[str]:
        """Yields SSE frames until the client disconnects (which cancels this generator)."""
        queue = self.subscribe(topic)
        try:
            yield CONNECTED_FRAME
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
                except TimeoutError:
                    yield HEARTBEAT_FRAME
                    continue
                yield format_sse(event)
        finally:
            self.unsubscribe(topic, queue)

broadcaster = Broadcaster()