from __future__ import annotations

import asyncio
import threading
import uuid
from enum import Enum

from api.models import NetworkConfig, RouterConfig, SchedulerConfig, ServerQueuePolicyConfig
from api.policy_registry import registry as policy_registry
from des.network.network import QueueingNetwork
from des.network.routing import (
    ClassBasedRouter,
    ProbabilisticRouter,
    RoundRobinRouter,
    RoutingPolicy,
)
from des.network.scheduling import (
    FirstNonEmptySchedulingPolicy,
    LongestQueueSchedulingPolicy,
    RoundRobinSchedulingPolicy,
    SchedulingPolicy,
)
from des.network.server_queue import (
    FbfsServerQueuePolicy,
    FifoServerQueuePolicy,
    LbfsServerQueuePolicy,
    ServerQueuePolicy,
)


def _build_router(cfg: RouterConfig) -> RoutingPolicy:
    if cfg.type == "probabilistic":
        return ProbabilisticRouter()
    if cfg.type == "round_robin":
        return RoundRobinRouter()
    if cfg.type == "class_based":
        if not cfg.class_map:
            raise ValueError("class_based router requires class_map")
        return ClassBasedRouter(cfg.class_map, fallback=cfg.fallback)
    if cfg.type == "custom":
        if not cfg.policy_id:
            raise ValueError("custom router requires policy_id")
        return policy_registry.build_router(cfg.policy_id)
    raise ValueError(f"Unknown router type: {cfg.type}")


def _build_scheduler(cfg: SchedulerConfig | None) -> SchedulingPolicy:
    if cfg is None or cfg.type == "round_robin":
        return RoundRobinSchedulingPolicy()
    if cfg.type == "first_non_empty":
        return FirstNonEmptySchedulingPolicy()
    if cfg.type == "longest_queue":
        return LongestQueueSchedulingPolicy()
    if cfg.type == "custom":
        if not cfg.policy_id:
            raise ValueError("custom scheduler requires policy_id")
        return policy_registry.build_station_scheduler(cfg.policy_id)
    raise ValueError(f"Unknown scheduler type: {cfg.type}")


def _build_server_queue_policy(cfg: ServerQueuePolicyConfig | None) -> ServerQueuePolicy:
    if cfg is None or cfg.type == "fifo":
        return FifoServerQueuePolicy()
    if cfg.type == "fbfs":
        return FbfsServerQueuePolicy()
    if cfg.type == "lbfs":
        return LbfsServerQueuePolicy()
    if cfg.type == "custom":
        if not cfg.policy_id:
            raise ValueError("custom server queue policy requires policy_id")
        return policy_registry.build_server_queue_policy(cfg.policy_id)
    raise ValueError(f"Unknown server queue policy type: {cfg.type}")


class SessionStatus(str, Enum):
    IDLE = "idle"
    PAUSED = "paused"
    RUNNING = "running"
    DONE = "done"


class SimulationSession:
    def __init__(self, session_id: str, config: NetworkConfig, net: QueueingNetwork) -> None:
        self.id = session_id
        self.config = config
        self.net = net
        self.status = SessionStatus.IDLE
        self.event_count: int = 0
        self._initialized = False
        self._stop_event = threading.Event()
        # asyncio queue for streaming; populated by background thread
        self._stream_queue: asyncio.Queue | None = None

    @staticmethod
    def from_config(session_id: str, config: NetworkConfig) -> "SimulationSession":
        net = QueueingNetwork(warm_up_time=config.warm_up_time)

        source_ids = set()
        server_ids = set()
        sink_ids = set()

        for node in config.nodes:
            if node.type == "source":
                if node.arrival_rate is None or node.next_node_id is None:
                    raise ValueError(f"Source '{node.id}' requires arrival_rate and next_node_id")
                net.add_source(
                    node.id,
                    arrival_rate=node.arrival_rate,
                    next_node_id=node.next_node_id,
                    customer_class=node.customer_class,
                )
                source_ids.add(node.id)
            elif node.type == "server":
                if node.service_rate is None:
                    raise ValueError(f"Server '{node.id}' requires service_rate")
                net.add_server(
                    node.id,
                    service_rate=node.service_rate,
                    c=node.c,
                    queue_policy=_build_server_queue_policy(node.queue_policy),
                )
                server_ids.add(node.id)
            elif node.type == "buffer":
                net.add_buffer(node.id)
            elif node.type == "station":
                if node.service_rate is None:
                    raise ValueError(f"Station '{node.id}' requires service_rate")
                net.add_station(
                    node.id,
                    service_rate=node.service_rate,
                    c=node.c,
                    scheduler=_build_scheduler(node.scheduler),
                )
            elif node.type == "sink":
                net.add_sink(node.id)
                sink_ids.add(node.id)

        for edge in config.edges:
            net.add_edge(edge.source, edge.target, weight=edge.weight)

        # global default router
        net.set_router(_build_router(config.default_router))

        # per-node routers for servers
        for node in config.nodes:
            if node.type == "server" and node.router is not None:
                net.set_node_router(node.id, _build_router(node.router))

        return SimulationSession(session_id, config, net)

    def get_state(self) -> dict:
        state = self.net.observe_system()
        return {
            "sim_time": self.net.sim.clock,
            "event_count": self.event_count,
            "status": self.status,
            **state,
        }

    def get_stats(self) -> list[dict]:
        return self.net.stats()

    def initialize(self) -> None:
        if self._initialized:
            return
        self.net.start()
        self._initialized = True

    def step(self) -> dict:
        if self.status == SessionStatus.DONE:
            return self.get_state()
        self.initialize()
        self.net.sim.step()
        self.event_count += 1
        if self.net.sim.scheduler.is_empty():
            self.status = SessionStatus.DONE
        else:
            self.status = SessionStatus.PAUSED
        return self.get_state()

    def stop(self) -> None:
        self._stop_event.set()
        if self.status == SessionStatus.RUNNING:
            self.status = SessionStatus.PAUSED


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, SimulationSession] = {}
        self._lock = threading.Lock()

    def create(self, config: NetworkConfig) -> SimulationSession:
        session_id = str(uuid.uuid4())
        session = SimulationSession.from_config(session_id, config)
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> SimulationSession | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session:
            session.stop()
        return session is not None

    def list_ids(self) -> list[str]:
        return list(self._sessions.keys())


# Singleton manager shared across the app
manager = SessionManager()
