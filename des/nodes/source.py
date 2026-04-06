from __future__ import annotations

import random
from typing import TYPE_CHECKING, Callable

from des.engine.event import EventType
from des.nodes.base import Node

if TYPE_CHECKING:
    from des.engine.event import Event
    from des.engine.simulation import Simulation


class Source(Node):
    """Generates customers according to a configurable inter-arrival distribution."""

    def __init__(
        self,
        node_id: str,
        simulation: Simulation,
        next_node_id: str,
        arrival_rate: float,
        inter_arrival_fn: Callable[[], float] | None = None,
        customer_class: str | None = None,
    ) -> None:
        super().__init__(node_id, simulation)
        self.next_node_id = next_node_id
        self.arrival_rate = arrival_rate
        self._inter_arrival_fn = inter_arrival_fn or (lambda: random.expovariate(arrival_rate))
        self._customer_count: int = 0
        self.customer_class = customer_class

    def start(self) -> None:
        delay = self._inter_arrival_fn()
        self.sim.scheduler.schedule(
            time=self.sim.clock + delay,
            event_type=EventType.ARRIVAL,
            target_id=self.node_id,
        )

    def handle(self, event: Event) -> None:
        self._customer_count += 1
        customer: dict = {"id": self._customer_count, "arrival_time": self.sim.clock}
        if self.customer_class is not None:
            customer["class"] = self.customer_class

        self.sim.scheduler.schedule(
            time=self.sim.clock,
            event_type=EventType.ARRIVAL,
            target_id=self.next_node_id,
            payload=customer,
        )

        delay = self._inter_arrival_fn()
        self.sim.scheduler.schedule(
            time=self.sim.clock + delay,
            event_type=EventType.ARRIVAL,
            target_id=self.node_id,
        )

    @property
    def customer_count(self) -> int:
        return self._customer_count
