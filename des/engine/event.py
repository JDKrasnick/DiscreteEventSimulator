from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class EventType(Enum):
    ARRIVAL = auto()
    SERVICE_START = auto()
    DEPARTURE = auto()


@dataclass(order=True, frozen=True)
class Event:
    time: float
    seq: int
    type: EventType = field(compare=False)
    target_id: str = field(compare=False)
    payload: Any = field(compare=False, default=None)
