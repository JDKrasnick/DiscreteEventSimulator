from __future__ import annotations

from typing import Any

import networkx as nx

from des.engine.simulation import Simulation
from des.network.routing import ClassBasedRouter, ProbabilisticRouter, RoutingPolicy
from des.nodes.server import MMcServer
from des.nodes.sink import Sink
from des.nodes.source import Source


class QueueingNetwork:
    """
    Assembles a network of sources, servers, and sinks connected via a
    directed graph. Edge weights are routing probabilities.
    """

    def __init__(self, warm_up_time: float = 0.0) -> None:
        self.sim = Simulation(warm_up_time=warm_up_time)
        self._graph: nx.DiGraph = nx.DiGraph()
        self._sources: list[Source] = []
        self._servers: dict[str, MMcServer] = {}
        self._sinks: dict[str, Sink] = {}
        self._router: RoutingPolicy = ProbabilisticRouter()

    # ------------------------------------------------------------------
    # Building the network
    # ------------------------------------------------------------------

    def add_source(
        self,
        node_id: str,
        arrival_rate: float,
        next_node_id: str,
        customer_class: str | None = None,
    ) -> Source:
        source = Source(node_id, self.sim, next_node_id=next_node_id, arrival_rate=arrival_rate, customer_class=customer_class)
        self._graph.add_node(node_id, kind="source", arrival_rate=arrival_rate)
        self._sources.append(source)
        return source

    def add_server(
        self,
        node_id: str,
        service_rate: float,
        c: int = 1,
    ) -> MMcServer:
        # next_node_id will be resolved dynamically via routing at departure
        server = _RoutedServer(node_id, self.sim, service_rate=service_rate, c=c, network=self)
        self._graph.add_node(node_id, kind="server", service_rate=service_rate, c=c)
        self._servers[node_id] = server
        return server

    def add_sink(self, node_id: str) -> Sink:
        sink = Sink(node_id, self.sim)
        self._graph.add_node(node_id, kind="sink")
        self._sinks[node_id] = sink
        return sink

    def add_edge(self, src: str, dst: str, weight: float = 1.0) -> None:
        self._graph.add_edge(src, dst, weight=weight)

    def set_router(self, policy: RoutingPolicy) -> None:
        self._router = policy

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------

    def validate(self) -> None:
        for node_id in self._graph.nodes:
            kind = self._graph.nodes[node_id].get("kind")
            if kind == "source":
                continue
            if self._graph.in_degree(node_id) == 0:
                raise ValueError(f"Node '{node_id}' has no incoming edges.")
        sinks = [n for n, d in self._graph.nodes(data=True) if d.get("kind") == "sink"]
        if not sinks:
            raise ValueError("Network has no sink nodes.")

    def run(self, until: float, cli: bool = False, refresh_interval: float = 10.0) -> None:
        if cli:
            from des.viz.cli import run_with_cli
            run_with_cli(self, until=until, refresh_interval=refresh_interval)
            return
        self.validate()
        for source in self._sources:
            source.start()
        self.sim.run(until=until)

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def successors(self, node_id: str) -> list[tuple[str, float]]:
        """Return [(successor_id, weight), ...] for the given node."""
        return [
            (dst, data.get("weight", 1.0))
            for dst, data in self._graph[node_id].items()
        ]

    def route(self, customer: dict, from_node_id: str) -> str:
        succs = self.successors(from_node_id)
        return self._router.next_node(customer, succs)

    @property
    def graph(self) -> nx.DiGraph:
        return self._graph

    def stats(self) -> list[dict]:
        return [s.collector.summary(self.sim.clock) for s in self._servers.values()]


class _RoutedServer(MMcServer):
    """MMcServer that resolves its next node via the network's routing policy."""

    def __init__(self, node_id: str, simulation: Simulation, service_rate: float, c: int, network: QueueingNetwork) -> None:
        super().__init__(node_id, simulation, service_rate=service_rate, c=c, next_node_id=None)
        self._network = network

    def _on_departure(self, event: Any) -> None:
        customer = event.payload
        self._busy_servers -= 1

        if self.sim.warmed_up:
            sojourn = self.sim.clock - customer["arrival_time"]
            wait = customer["service_start_time"] - customer["queue_entry_time"]
            self.collector.record_departure(self.sim.clock, sojourn, wait)

        succs = self._network.successors(self.node_id)
        if succs:
            next_id = self._network.route(customer, self.node_id)
            from des.engine.event import EventType
            self.sim.scheduler.schedule(
                time=self.sim.clock,
                event_type=EventType.ARRIVAL,
                target_id=next_id,
                payload=customer,
            )

        if self._queue:
            next_customer = self._queue.popleft()
            self._start_service(next_customer)

        self._record_snapshot()
