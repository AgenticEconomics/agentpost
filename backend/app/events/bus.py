"""Event bus - in-process pub/sub for real-time events."""
from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Event:
    type: str
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"type": self.type, "data": self.data, "timestamp": self.timestamp}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._global_subs: list[asyncio.Queue] = []

    def subscribe(self, pattern: str = "*") -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        if pattern == "*":
            self._global_subs.append(q)
        else:
            self._subscribers[pattern].append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue, pattern: str = "*") -> None:
        if pattern == "*":
            if q in self._global_subs:
                self._global_subs.remove(q)
        else:
            subs = self._subscribers.get(pattern, [])
            if q in subs:
                subs.remove(q)

    def publish(self, event: Event) -> None:
        for q in self._global_subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
        for pattern, queues in self._subscribers.items():
            if event.type.startswith(pattern) or pattern == "*":
                for q in queues:
                    try:
                        q.put_nowait(event)
                    except asyncio.QueueFull:
                        pass

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        self.publish(Event(type=event_type, data=data))


bus = EventBus()
