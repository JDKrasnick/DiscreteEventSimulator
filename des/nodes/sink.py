from __future__ import annotations

from typing import TYPE_CHECKING

from des.engine.event import EventType
from des.nodes.base import Node

if TYPE_CHECKING:
    from des.engine.event import Event
    from des.engine.simulation import Simulation


class Sink(Node):
    def __init__(self, node_id: str, simulation: Simulation) -> None:
        super().__init__(node_id, simulation)
        self._count: int = 0
        self._total_sojourn: float = 0.0

    def handle(self, event: Event) -> None:
        if event.type != EventType.ARRIVAL:
            return
        self._count += 1
        customer = event.payload
        if customer is not None and isinstance(customer, dict) and "arrival_time" in customer:
            self._total_sojourn += self.sim.clock - customer["arrival_time"]

    @property
    def count(self) -> int:
        return self._count

    @property
    def mean_sojourn(self) -> float:
        return self._total_sojourn / self._count if self._count > 0 else 0.0
