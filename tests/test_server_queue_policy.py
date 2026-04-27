from __future__ import annotations

import pytest

from des.engine.event import EventType
from des.engine.simulation import Simulation
from des.network import (
    CallbackServerQueuePolicy,
    FbfsServerQueuePolicy,
    FifoServerQueuePolicy,
    LbfsServerQueuePolicy,
    NetworkConfig,
    QueueingNetwork,
)
from des.network.routing import RoundRobinRouter
from des.nodes.server import MMcServer
from des.nodes.sink import Sink


def _job(job_id: int, *, stage: int = 0, customer_class: str | None = None) -> dict:
    payload = {"id": job_id, "arrival_time": 0.0, "stage": stage}
    if customer_class is not None:
        payload["class"] = customer_class
    return payload


def _next_departure_job_id(
    *,
    queue_policy=None,
    discipline=None,
    queued_jobs: list[dict] | None = None,
) -> int:
    sim = Simulation()
    server_kwargs = {
        "node_id": "srv",
        "simulation": sim,
        "service_rate": 1.0,
        "c": 1,
        "next_node_id": "sink",
        "service_time_fn": lambda: 10.0,
    }
    if queue_policy is not None:
        server_kwargs["queue_policy"] = queue_policy
    if discipline is not None:
        server_kwargs["discipline"] = discipline
    MMcServer(**server_kwargs)
    Sink("sink", sim)

    jobs = [_job(1, stage=99)] + (queued_jobs or [_job(2, stage=1), _job(3, stage=2)])
    for time, job in enumerate(jobs):
        sim.scheduler.schedule(float(time), EventType.ARRIVAL, "srv", job)

    for _ in range(len(jobs) + 1):
        sim.step()

    departures = [
        event for event in sim.scheduler._heap
        if event.type == EventType.DEPARTURE and event.target_id == "srv"
    ]
    assert len(departures) == 1
    return departures[0].payload["id"]


def test_fifo_server_queue_policy_serves_oldest_waiting_job():
    assert _next_departure_job_id(queue_policy=FifoServerQueuePolicy()) == 2


def test_fbfs_server_queue_policy_serves_smallest_stage():
    selected_job = _next_departure_job_id(
        queue_policy=FbfsServerQueuePolicy(),
        queued_jobs=[_job(2, stage=5), _job(3, stage=1)],
    )
    assert selected_job == 3


def test_lbfs_server_queue_policy_serves_largest_stage():
    selected_job = _next_departure_job_id(
        queue_policy=LbfsServerQueuePolicy(),
        queued_jobs=[_job(2, stage=1), _job(3, stage=5)],
    )
    assert selected_job == 3


def test_callback_server_queue_policy_can_select_arbitrary_waiting_job():
    selected_job = _next_departure_job_id(
        queue_policy=CallbackServerQueuePolicy(lambda _server, _jobs: 1),
    )
    assert selected_job == 3


def test_invalid_callback_queue_index_raises_clear_error():
    sim = Simulation()
    MMcServer(
        "srv",
        sim,
        service_rate=1.0,
        c=1,
        next_node_id="sink",
        service_time_fn=lambda: 10.0,
        queue_policy=CallbackServerQueuePolicy(lambda _server, _jobs: 5),
    )
    Sink("sink", sim)

    for time, job in enumerate([_job(1), _job(2), _job(3)]):
        sim.scheduler.schedule(float(time), EventType.ARRIVAL, "srv", job)

    for _ in range(3):
        sim.step()

    with pytest.raises(ValueError, match="invalid index 5"):
        sim.step()


@pytest.mark.parametrize("queue_policy", [FifoServerQueuePolicy(), LbfsServerQueuePolicy()])
def test_routing_behavior_is_unchanged_when_queue_policy_changes(queue_policy):
    net = QueueingNetwork()
    server = net.add_server("srv", service_rate=1.0, queue_policy=queue_policy)
    server._service_time_fn = lambda: 5.0
    net.add_sink("sink_a")
    net.add_sink("sink_b")
    net.add_edge("srv", "sink_a")
    net.add_edge("srv", "sink_b")
    net.set_node_router("srv", RoundRobinRouter())

    for time, job in enumerate([_job(1, customer_class="A"), _job(2, customer_class="B"), _job(3, customer_class="A")]):
        net.sim.scheduler.schedule(float(time), EventType.ARRIVAL, "srv", job)

    for _ in range(8):
        net.sim.step()

    assert net._sinks["sink_a"].count == 1
    assert net._sinks["sink_b"].count == 1
    assert net.graph.nodes["srv"]["router_type"] == "RoundRobinRouter"


def test_network_config_queue_policy_round_trips_through_from_config():
    config = NetworkConfig()
    config.add_source("src", arrival_rate=0.5, next_node_id="srv")
    config.add_server("srv", service_rate=1.0, queue_policy=FbfsServerQueuePolicy())
    config.add_sink("sink")
    config.add_edge("src", "srv")
    config.add_edge("srv", "sink")

    net = QueueingNetwork.from_config(config)

    assert isinstance(net.servers["srv"].queue_policy, FbfsServerQueuePolicy)
    assert net.graph.nodes["srv"]["queue_policy_type"] == "FbfsServerQueuePolicy"


def test_set_server_policy_updates_server_and_graph_metadata():
    net = QueueingNetwork()
    net.add_server("srv", service_rate=1.0)

    net.set_server_policy("srv", LbfsServerQueuePolicy())

    assert isinstance(net.servers["srv"].queue_policy, LbfsServerQueuePolicy)
    assert net.graph.nodes["srv"]["queue_policy_type"] == "LbfsServerQueuePolicy"


def test_deprecated_discipline_maps_to_queue_policy_layer():
    with pytest.deprecated_call():
        config = NetworkConfig()
        config.add_source("src", arrival_rate=0.5, next_node_id="srv")
        config.add_server("srv", service_rate=1.0, discipline="FBFS")
        config.add_sink("sink")
        config.add_edge("src", "srv")
        config.add_edge("srv", "sink")

    with pytest.deprecated_call():
        net = QueueingNetwork.from_config(config)

    assert isinstance(net.servers["srv"].queue_policy, FbfsServerQueuePolicy)


def test_queue_policy_wins_when_both_queue_policy_and_discipline_are_supplied():
    selected_job = _next_departure_job_id(
        queue_policy=FifoServerQueuePolicy(),
        discipline="LBFS",
        queued_jobs=[_job(2, stage=1), _job(3, stage=5)],
    )
    assert selected_job == 2
