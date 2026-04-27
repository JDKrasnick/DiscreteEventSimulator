from __future__ import annotations

from typing import TYPE_CHECKING

from des.engine.event import EventType
from des.nodes.base import Node
from des.stats.collector import Collector

if TYPE_CHECKING:
    from des.engine.event import Event
    from des.engine.simulation import Simulation
    from des.network.network import QueueingNetwork
    from des.nodes.station import Station


class Buffer(Node):
    """Passive queue that stores jobs until an attached station pulls one."""

    def __init__(self, node_id: str, simulation: Simulation, network: QueueingNetwork) -> None:
        super().__init__(node_id, simulation)
        self._network = network
        self._queue: list[dict] = []
        self.collector = Collector(node_id=node_id, node_kind="buffer")
        self._snapshots: list[tuple[float, int]] = []

    def handle(self, event: Event) -> None:
        if event.type != EventType.ARRIVAL:
            return

        customer = event.payload
        if customer is None:
            return
        customer["_current_buffer_entry_time"] = self.sim.clock
        self._queue.append(customer)

        if self.sim.warmed_up:
            self.collector.record_arrival(self.sim.clock)

        self._record_snapshot()
        for station in self._downstream_stations():
            station.maybe_request_decision()

    def dequeue(self) -> dict:
        if not self._queue:
            raise IndexError(f"Buffer '{self.node_id}' is empty")

        customer = self._queue.pop(0)
        if self.sim.warmed_up:
            entry_time = customer.pop("_current_buffer_entry_time", self.sim.clock)
            wait = self.sim.clock - entry_time
            self.collector.record_departure(self.sim.clock, wait, wait)
        else:
            customer.pop("_current_buffer_entry_time", None)

        self._record_snapshot()
        return customer

    def _downstream_stations(self) -> list[Station]:
        return [
            station
            for station_id, station in self._network.stations.items()
            if self._network.graph.has_edge(self.node_id, station_id)
        ]

    def _record_snapshot(self) -> None:
        q = len(self._queue)
        self._snapshots.append((self.sim.clock, q))
        if self.sim.warmed_up:
            if not self.collector.queue_length.initialized:
                self.collector.queue_length.start(self.sim.clock, q)
                self.collector.system_length.start(self.sim.clock, q)
            else:
                self.collector.queue_length.update(self.sim.clock, q)
                self.collector.system_length.update(self.sim.clock, q)

    @property
    def queue_length(self) -> int:
        return len(self._queue)

    @property
    def jobs(self) -> list[dict]:
        return list(self._queue)

    @property
    def snapshots(self) -> list[tuple[float, int]]:
        return self._snapshots
