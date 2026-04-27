from __future__ import annotations

import random
from typing import TYPE_CHECKING, Callable

from des.engine.event import EventType
from des.network.server_queue import (
    Discipline,
    ServerQueuePolicy,
    _UNSET_DISCIPLINE,
    resolve_server_queue_policy,
)
from des.nodes.base import Node
from des.stats.collector import Collector

if TYPE_CHECKING:
    from des.engine.event import Event
    from des.engine.simulation import Simulation


class MMcServer(Node):
    """M/M/c server: c parallel servers, exponential service times, pluggable queue policy."""

    def __init__(
        self,
        node_id: str,
        simulation: Simulation,
        service_rate: float,
        c: int = 1,
        next_node_id: str | None = None,
        service_time_fn: Callable[[], float] | None = None,
        queue_policy: ServerQueuePolicy | None = None,
        discipline: Discipline | object = _UNSET_DISCIPLINE,
    ) -> None:
        super().__init__(node_id, simulation)
        self.service_rate = service_rate
        self.c = c
        self.next_node_id = next_node_id
        self._service_time_fn = service_time_fn or (lambda: random.expovariate(service_rate))
        self._queue_policy: ServerQueuePolicy = resolve_server_queue_policy(
            queue_policy,
            discipline,
            warn_on_deprecated_discipline=True,
            context="discipline",
        )
        self._queue: list[dict] = []
        self._busy_servers: int = 0
        self.collector = Collector(node_id=node_id, node_kind="server")
        self._snapshots: list[tuple[float, int, int]] = []  # (time, queue_len, system_len)

    def _record_snapshot(self) -> None:
        q = len(self._queue)
        n = q + self._busy_servers
        self._snapshots.append((self.sim.clock, q, n))
        if self.sim.warmed_up:
            if not self.collector.queue_length.initialized:
                self.collector.queue_length.start(self.sim.clock, q)
                self.collector.system_length.start(self.sim.clock, n)
            else:
                self.collector.queue_length.update(self.sim.clock, q)
                self.collector.system_length.update(self.sim.clock, n)

    def handle(self, event: Event) -> None:
        if event.type == EventType.ARRIVAL:
            self._on_arrival(event)
        elif event.type == EventType.DEPARTURE:
            self._on_departure(event)

    def _select_next(self) -> dict:
        jobs = list(self._queue)
        idx = self._queue_policy.choose_job(self, jobs)
        if not isinstance(idx, int) or isinstance(idx, bool):
            raise ValueError(
                f"Server queue policy {type(self._queue_policy).__name__} returned non-integer index "
                f"{idx!r} for server '{self.node_id}'."
            )
        if idx < 0 or idx >= len(self._queue):
            raise ValueError(
                f"Server queue policy {type(self._queue_policy).__name__} returned invalid index "
                f"{idx} for {len(self._queue)} waiting jobs on server '{self.node_id}'."
            )
        job = self._queue[idx]
        self._queue.pop(idx)
        return job

    def _on_arrival(self, event: Event) -> None:
        customer = event.payload
        customer["queue_entry_time"] = self.sim.clock

        if self.sim.warmed_up:
            self.collector.record_arrival(self.sim.clock)

        if self._busy_servers < self.c:
            self._start_service(customer)
        else:
            self._queue.append(customer)

        self._record_snapshot()

    def _start_service(self, customer: dict) -> None:
        self._busy_servers += 1
        customer["service_start_time"] = self.sim.clock
        service_time = self._service_time_fn()
        self.sim.scheduler.schedule(
            time=self.sim.clock + service_time,
            event_type=EventType.DEPARTURE,
            target_id=self.node_id,
            payload=customer,
        )

    def _on_departure(self, event: Event) -> None:
        customer = event.payload
        self._busy_servers -= 1

        if self.sim.warmed_up:
            sojourn = self.sim.clock - customer["arrival_time"]
            wait = customer["service_start_time"] - customer["queue_entry_time"]
            self.collector.record_departure(self.sim.clock, sojourn, wait)

        if self.next_node_id is not None:
            self.sim.scheduler.schedule(
                time=self.sim.clock,
                event_type=EventType.ARRIVAL,
                target_id=self.next_node_id,
                payload=customer,
            )

        if self._queue:
            self._start_service(self._select_next())

        self._record_snapshot()

    @property
    def utilization(self) -> float:
        return self._busy_servers / self.c

    @property
    def queue_length(self) -> int:
        return len(self._queue)

    @property
    def jobs(self) -> list[dict]:
        """All jobs currently waiting in the queue."""
        return list(self._queue)

    @property
    def queue_policy(self) -> ServerQueuePolicy:
        return self._queue_policy

    def set_queue_policy(self, policy: ServerQueuePolicy) -> None:
        self._queue_policy = policy

    @property
    def snapshots(self) -> list[tuple[float, int, int]]:
        return self._snapshots


MM1Server = lambda node_id, simulation, service_rate, **kwargs: MMcServer(
    node_id=node_id, simulation=simulation, service_rate=service_rate, c=1, **kwargs
)
