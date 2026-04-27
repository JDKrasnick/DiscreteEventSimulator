from __future__ import annotations

import random
from typing import TYPE_CHECKING, Callable

from des.engine.event import EventType
from des.network.scheduling import RoundRobinSchedulingPolicy, SchedulingPolicy
from des.nodes.base import Node

if TYPE_CHECKING:
    from des.engine.event import Event
    from des.engine.simulation import Simulation
    from des.network.network import QueueingNetwork
    from des.nodes.buffer import Buffer


class Station(Node):
    """Shared service resource that pulls jobs from explicit upstream buffers."""

    def __init__(
        self,
        node_id: str,
        simulation: Simulation,
        network: QueueingNetwork,
        service_rate: float,
        c: int = 1,
        service_time_fn: Callable[[], float] | None = None,
        scheduler: SchedulingPolicy | None = None,
    ) -> None:
        super().__init__(node_id, simulation)
        self._network = network
        self.service_rate = service_rate
        self.c = c
        self._service_time_fn = service_time_fn or (lambda: random.expovariate(service_rate))
        self._scheduler: SchedulingPolicy = scheduler or RoundRobinSchedulingPolicy()
        self._busy_servers = 0
        self._completed_jobs = 0
        self._decision_pending = False

    def handle(self, event: Event) -> None:
        if event.type == EventType.SCHEDULING_DECISION:
            self._decision_pending = False
            self._on_scheduling_decision()
        elif event.type == EventType.DEPARTURE:
            self._on_departure(event)

    def maybe_request_decision(self) -> None:
        if self._decision_pending or self.idle_servers <= 0 or not self.has_waiting_work:
            return
        self._decision_pending = True
        self.sim.scheduler.schedule(
            time=self.sim.clock,
            event_type=EventType.SCHEDULING_DECISION,
            target_id=self.node_id,
        )

    def _on_scheduling_decision(self) -> None:
        if self.idle_servers <= 0:
            return
        buffer = self._select_buffer()
        if buffer is None:
            return
        customer = buffer.dequeue()
        customer["service_start_time"] = self.sim.clock
        customer["service_station_id"] = self.node_id
        self._busy_servers += 1
        self.sim.scheduler.schedule(
            time=self.sim.clock + self._service_time_fn(),
            event_type=EventType.DEPARTURE,
            target_id=self.node_id,
            payload=customer,
        )
        if self.idle_servers > 0 and self.has_waiting_work:
            self.maybe_request_decision()

    def _on_departure(self, event: Event) -> None:
        customer = event.payload
        self._busy_servers -= 1
        self._completed_jobs += 1

        next_node_id = self._network.station_successor(self.node_id)
        if next_node_id is not None:
            self.sim.scheduler.schedule(
                time=self.sim.clock,
                event_type=EventType.ARRIVAL,
                target_id=next_node_id,
                payload=customer,
            )

        self.maybe_request_decision()

    def _select_buffer(self) -> Buffer | None:
        buffers = self.upstream_buffers
        if not buffers:
            return None

        choice = self._scheduler.choose_buffer(self, buffers)
        if choice is None:
            return None

        start_idx = self._normalize_choice(choice, buffers)
        if start_idx is None:
            return None

        for offset in range(len(buffers)):
            buffer = buffers[(start_idx + offset) % len(buffers)]
            if buffer.queue_length > 0:
                return buffer
        return None

    def _normalize_choice(self, choice: int | str, buffers: list[Buffer]) -> int | None:
        if isinstance(choice, str):
            for idx, buffer in enumerate(buffers):
                if buffer.node_id == choice:
                    return idx
            return None
        return choice % len(buffers) if buffers else None

    @property
    def upstream_buffers(self) -> list[Buffer]:
        return self._network.station_upstream_buffers(self.node_id)

    @property
    def has_waiting_work(self) -> bool:
        return any(buffer.queue_length > 0 for buffer in self.upstream_buffers)

    @property
    def busy_servers(self) -> int:
        return self._busy_servers

    @property
    def idle_servers(self) -> int:
        return self.c - self._busy_servers

    @property
    def utilization(self) -> float:
        return self._busy_servers / self.c

    @property
    def completed_jobs(self) -> int:
        return self._completed_jobs

    def set_scheduler(self, scheduler: SchedulingPolicy) -> None:
        self._scheduler = scheduler
