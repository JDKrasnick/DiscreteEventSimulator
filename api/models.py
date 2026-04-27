from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RouterConfig(BaseModel):
    type: Literal["probabilistic", "round_robin", "class_based", "custom"] = "probabilistic"
    class_map: dict[str, str] | None = None  # class_based only
    fallback: str | None = None
    policy_id: str | None = None  # custom only


class SchedulerConfig(BaseModel):
    type: Literal["round_robin", "first_non_empty", "longest_queue", "custom"] = "round_robin"
    policy_id: str | None = None  # custom only


class ServerQueuePolicyConfig(BaseModel):
    type: Literal["fifo", "fbfs", "lbfs", "custom"] = "fifo"
    policy_id: str | None = None  # custom only


class NodeConfig(BaseModel):
    id: str
    type: Literal["source", "server", "sink", "buffer", "station"]
    # source
    arrival_rate: float | None = None
    customer_class: str | None = None
    next_node_id: str | None = None
    # server
    service_rate: float | None = None
    c: int = 1
    router: RouterConfig | None = None  # per-node routing override
    queue_policy: ServerQueuePolicyConfig | None = None
    # station
    scheduler: SchedulerConfig | None = None


class EdgeConfig(BaseModel):
    source: str
    target: str
    weight: float = 1.0


class NetworkConfig(BaseModel):
    warm_up_time: float = 0.0
    nodes: list[NodeConfig]
    edges: list[EdgeConfig]
    default_router: RouterConfig = Field(default_factory=lambda: RouterConfig(type="probabilistic"))


class RunParams(BaseModel):
    until: float
    stream_interval: float = 0.5  # seconds between WS state pushes
