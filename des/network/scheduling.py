from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from des.nodes.buffer import Buffer
    from des.nodes.station import Station


class SchedulingPolicy(ABC):
    @abstractmethod
    def choose_buffer(self, station: Station, buffers: list[Buffer]) -> int | str | None:
        """Return a preferred upstream buffer index or id."""
        ...


class RoundRobinSchedulingPolicy(SchedulingPolicy):
    def __init__(self) -> None:
        self._index = 0

    def choose_buffer(self, station: Station, buffers: list[Buffer]) -> int | str | None:
        if not buffers:
            return None
        index = self._index % len(buffers)
        self._index += 1
        return index


class FirstNonEmptySchedulingPolicy(SchedulingPolicy):
    def choose_buffer(self, station: Station, buffers: list[Buffer]) -> int | str | None:
        return 0 if buffers else None


class LongestQueueSchedulingPolicy(SchedulingPolicy):
    def choose_buffer(self, station: Station, buffers: list[Buffer]) -> int | str | None:
        if not buffers:
            return None
        return max(range(len(buffers)), key=lambda idx: buffers[idx].queue_length)


class CallbackSchedulingPolicy(SchedulingPolicy):
    def __init__(self, fn: Callable[[Station, list[Buffer]], int | str | None]) -> None:
        self.fn = fn

    def choose_buffer(self, station: Station, buffers: list[Buffer]) -> int | str | None:
        return self.fn(station, buffers)
