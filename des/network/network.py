from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from des.engine.simulation import Simulation
from des.network.routing import ClassBasedRouter, ProbabilisticRouter, RoutingPolicy
from des.network.scheduling import RoundRobinSchedulingPolicy, SchedulingPolicy
from des.network.server_queue import (
    Discipline,
    ServerQueuePolicy,
    _UNSET_DISCIPLINE,
    resolve_server_queue_policy,
)
from des.nodes.buffer import Buffer
from des.nodes.server import MMcServer
from des.nodes.sink import Sink
from des.nodes.station import Station
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
        self._buffers: dict[str, Buffer] = {}
        self._stations: dict[str, Station] = {}
        self._sinks: dict[str, Sink] = {}
        self._router: RoutingPolicy = ProbabilisticRouter()
        self._node_routers: dict[str, RoutingPolicy] = {}
        self._server_queue_policies: dict[str, ServerQueuePolicy] = {}
        self._station_schedulers: dict[str, SchedulingPolicy] = {}

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
        queue_policy: ServerQueuePolicy | None = None,
        discipline: Discipline | object = _UNSET_DISCIPLINE,
    ) -> MMcServer:
        server_queue_policy = resolve_server_queue_policy(
            queue_policy,
            discipline,
            warn_on_deprecated_discipline=True,
            context="discipline",
        )
        # next_node_id will be resolved dynamically via routing at departure
        server = _RoutedServer(
            node_id,
            self.sim,
            service_rate=service_rate,
            c=c,
            network=self,
            queue_policy=server_queue_policy,
        )
        self._graph.add_node(
            node_id,
            kind="server",
            service_rate=service_rate,
            c=c,
            queue_policy_type=type(server_queue_policy).__name__,
        )
        self._servers[node_id] = server
        self._server_queue_policies[node_id] = server_queue_policy
        return server

    def add_buffer(self, node_id: str) -> Buffer:
        buffer = Buffer(node_id, self.sim, network=self)
        self._graph.add_node(node_id, kind="buffer")
        self._buffers[node_id] = buffer
        return buffer

    def add_station(
        self,
        node_id: str,
        service_rate: float,
        c: int = 1,
        scheduler: SchedulingPolicy | None = None,
    ) -> Station:
        station_scheduler = scheduler or RoundRobinSchedulingPolicy()
        station = Station(
            node_id,
            self.sim,
            network=self,
            service_rate=service_rate,
            c=c,
            scheduler=station_scheduler,
        )
        self._graph.add_node(
            node_id,
            kind="station",
            service_rate=service_rate,
            c=c,
            scheduler_type=type(station_scheduler).__name__,
        )
        self._stations[node_id] = station
        self._station_schedulers[node_id] = station_scheduler
        return station

    def add_sink(self, node_id: str) -> Sink:
        sink = Sink(node_id, self.sim)
        self._graph.add_node(node_id, kind="sink")
        self._sinks[node_id] = sink
        return sink

    def add_edge(self, src: str, dst: str, weight: float = 1.0) -> None:
        self._graph.add_edge(src, dst, weight=weight)

    def set_router(self, policy: RoutingPolicy) -> None:
        self._router = policy

    def set_node_router(self, node_id: str, policy: RoutingPolicy) -> None:
        """Set a routing policy for a specific node, overriding the global default."""
        self._node_routers[node_id] = policy
        if node_id in self._graph.nodes:
            self._graph.nodes[node_id]["router_type"] = type(policy).__name__

    def set_station_scheduler(self, node_id: str, policy: SchedulingPolicy) -> None:
        if node_id not in self._stations:
            raise KeyError(f"Unknown station '{node_id}'")
        self._station_schedulers[node_id] = policy
        self._stations[node_id].set_scheduler(policy)
        self._graph.nodes[node_id]["scheduler_type"] = type(policy).__name__

    def set_server_policy(self, node_id: str, policy: ServerQueuePolicy) -> None:
        if node_id not in self._servers:
            raise KeyError(f"Unknown server '{node_id}'")
        self._server_queue_policies[node_id] = policy
        self._servers[node_id].set_queue_policy(policy)
        self._graph.nodes[node_id]["queue_policy_type"] = type(policy).__name__

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------

    def validate(self) -> None:
        for node_id in self._graph.nodes:
            kind = self._graph.nodes[node_id].get("kind")
            if kind == "source":
                continue
            if kind == "buffer":
                if self._graph.in_degree(node_id) == 0:
                    raise ValueError(f"Node '{node_id}' has no incoming edges.")
                invalid = [
                    succ for succ in self._graph.successors(node_id)
                    if self._graph.nodes[succ].get("kind") != "station"
                ]
                if invalid:
                    raise ValueError(
                        f"Buffer '{node_id}' may only connect to station nodes. Invalid successors: {invalid}"
                    )
            if kind == "station":
                preds = list(self._graph.predecessors(node_id))
                if not preds:
                    raise ValueError(f"Station '{node_id}' must have at least one incoming buffer.")
                invalid_preds = [
                    pred for pred in preds
                    if self._graph.nodes[pred].get("kind") != "buffer"
                ]
                if invalid_preds:
                    raise ValueError(
                        f"Station '{node_id}' may only receive work from buffers. Invalid predecessors: {invalid_preds}"
                    )
                succs = list(self._graph.successors(node_id))
                if len(succs) != 1:
                    raise ValueError(
                        f"Station '{node_id}' must have exactly one outgoing edge; found {len(succs)}."
                    )
                invalid_succs = [
                    succ for succ in succs
                    if self._graph.nodes[succ].get("kind") not in {"buffer", "sink", "server"}
                ]
                if invalid_succs:
                    raise ValueError(
                        f"Station '{node_id}' may only connect to buffer, sink, or server nodes. Invalid successors: {invalid_succs}"
                    )
            if kind not in {"buffer", "station"} and self._graph.in_degree(node_id) == 0:
                raise ValueError(f"Node '{node_id}' has no incoming edges.")
        sinks = [n for n, d in self._graph.nodes(data=True) if d.get("kind") == "sink"]
        if not sinks:
            raise ValueError("Network has no sink nodes.")

    def start(self) -> None:
        """Seed the event queue without running the simulation.

        Call this instead of run() when you want to drive the simulation
        manually via sim.step() (e.g. from a gym environment).
        """
        self.validate()
        for source in self._sources:
            source.start()

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
        router = self._node_routers.get(from_node_id, self._router)
        return router.next_node(customer, succs)

    @property
    def graph(self) -> nx.DiGraph:
        return self._graph

    @property
    def servers(self) -> dict[str, MMcServer]:
        return self._servers

    @property
    def buffers(self) -> dict[str, Buffer]:
        return self._buffers

    @property
    def stations(self) -> dict[str, Station]:
        return self._stations

    def observe(self) -> dict[str, dict]:
        """Return current per-server state as a plain dict.

        Keys per server: queue_length, busy_servers, utilization.
        Suitable for constructing gym observation vectors.
        """
        return {
            node_id: {
                "queue_length": server.queue_length,
                "busy_servers": server._busy_servers,
                "utilization": server.utilization,
            }
            for node_id, server in self._servers.items()
        }

    def observe_system(self) -> dict[str, dict[str, dict]]:
        return {
            "servers": self.observe(),
            "buffers": {
                node_id: {"queue_length": buffer.queue_length}
                for node_id, buffer in self._buffers.items()
            },
            "stations": {
                node_id: {
                    "busy_servers": station.busy_servers,
                    "idle_servers": station.idle_servers,
                    "utilization": station.utilization,
                    "completed_jobs": station.completed_jobs,
                }
                for node_id, station in self._stations.items()
            },
        }

    def stats(self) -> list[dict]:
        return (
            [s.collector.summary(self.sim.clock) for s in self._servers.values()]
            + [b.collector.summary(self.sim.clock) for b in self._buffers.values()]
        )

    def station_upstream_buffers(self, station_id: str) -> list[Buffer]:
        return [
            buffer
            for buffer_id, buffer in self._buffers.items()
            if self._graph.has_edge(buffer_id, station_id)
        ]

    def station_successor(self, station_id: str) -> str | None:
        succs = list(self._graph.successors(station_id))
        if not succs:
            return None
        return succs[0]

    @classmethod
    def from_config(cls, config: NetworkConfig) -> QueueingNetwork:
        net = cls(warm_up_time=config.warm_up_time)
        for src in config.sources:
            net.add_source(src.node_id, arrival_rate=src.arrival_rate, next_node_id=src.next_node_id, customer_class=src.customer_class)
        for srv in config.servers:
            net.add_server(
                srv.node_id,
                service_rate=srv.service_rate,
                c=srv.c,
                queue_policy=srv.queue_policy,
                discipline=srv.discipline,
            )
        for buf in config.buffers:
            net.add_buffer(buf.node_id)
        for station in config.stations:
            net.add_station(station.node_id, service_rate=station.service_rate, c=station.c, scheduler=station.scheduler)
        for sink_id in config.sinks:
            net.add_sink(sink_id)
        for u, v in config.edges:
            net.add_edge(u, v)
        return net


class _RoutedServer(MMcServer):
    """MMcServer that resolves its next node via the network's routing policy."""

    def __init__(
        self,
        node_id: str,
        simulation: Simulation,
        service_rate: float,
        c: int,
        network: QueueingNetwork,
        queue_policy: ServerQueuePolicy | None = None,
        discipline: Discipline | object = _UNSET_DISCIPLINE,
    ) -> None:
        super().__init__(
            node_id,
            simulation,
            service_rate=service_rate,
            c=c,
            next_node_id=None,
            queue_policy=queue_policy,
            discipline=discipline,
        )
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
            self._start_service(self._select_next())

        self._record_snapshot()

@dataclass
class SourceConfig:
    node_id: str
    arrival_rate: float
    next_node_id: str
    customer_class: str | None = None


@dataclass
class ServerConfig:
    node_id: str
    service_rate: float
    c: int = 1
    queue_policy: ServerQueuePolicy | None = None
    discipline: Discipline | None = None


@dataclass
class BufferConfig:
    node_id: str


@dataclass
class StationConfig:
    node_id: str
    service_rate: float
    c: int = 1
    scheduler: SchedulingPolicy | None = None


@dataclass
class NetworkConfig:
    warm_up_time: float = 0.0
    sources: list[SourceConfig] = field(default_factory=list)
    servers: list[ServerConfig] = field(default_factory=list)
    buffers: list[BufferConfig] = field(default_factory=list)
    stations: list[StationConfig] = field(default_factory=list)
    sinks: list[str] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)

    def add_source(self, node_id: str, arrival_rate: float, next_node_id: str, customer_class: str | None = None) -> None:
        self.sources.append(SourceConfig(node_id, arrival_rate, next_node_id, customer_class))

    def add_server(
        self,
        node_id: str,
        service_rate: float,
        c: int = 1,
        queue_policy: ServerQueuePolicy | None = None,
        discipline: Discipline | object = _UNSET_DISCIPLINE,
    ) -> None:
        if queue_policy is None and discipline is not _UNSET_DISCIPLINE:
            warnings.warn(
                "`discipline` is deprecated; use `queue_policy=` instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        resolved_discipline = None if discipline is _UNSET_DISCIPLINE else discipline
        self.servers.append(ServerConfig(node_id, service_rate, c, queue_policy, resolved_discipline))

    def add_buffer(self, node_id: str) -> None:
        self.buffers.append(BufferConfig(node_id))

    def add_station(
        self,
        node_id: str,
        service_rate: float,
        c: int = 1,
        scheduler: SchedulingPolicy | None = None,
    ) -> None:
        self.stations.append(StationConfig(node_id, service_rate, c, scheduler))

    def add_sink(self, node_id: str) -> None:
        self.sinks.append(node_id)

    def add_edge(self, src: str, dst: str) -> None:
        self.edges.append((src, dst))
