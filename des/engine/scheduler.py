from __future__ import annotations

import heapq
from typing import Any

from des.engine.event import Event, EventType


class Scheduler:
    def __init__(self) -> None:
        self._heap: list[Event] = []
        self._seq: int = 0

    def schedule(self, time: float, event_type: EventType, target_id: str, payload: Any = None) -> Event:
        event = Event(time=time, seq=self._seq, type=event_type, target_id=target_id, payload=payload)
        self._seq += 1
        heapq.heappush(self._heap, event)
        return event

    def pop_next(self) -> Event:
        return heapq.heappop(self._heap)

    def peek_time(self) -> float | None:
        return self._heap[0].time if self._heap else None

    def is_empty(self) -> bool:
        return len(self._heap) == 0

    def __len__(self) -> int:
        return len(self._heap)
