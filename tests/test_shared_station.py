import random

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from des.engine.event import EventType
from des.network import CallbackSchedulingPolicy, NetworkConfig, QueueingNetwork
from shared_station_gym import SharedStationSchedulingGym


def _job(job_id: int) -> dict:
    return {"id": job_id, "arrival_time": 0.0}


def _network_with_shared_station(c: int = 1) -> QueueingNetwork:
    net = QueueingNetwork()
    net.add_buffer("B1")
    net.add_buffer("B2")
    station = net.add_station("Station", service_rate=1.0, c=c)
    station._service_time_fn = lambda: 1.0
    net.add_sink("sink")
    net.add_edge("B1", "Station")
    net.add_edge("B2", "Station")
    net.add_edge("Station", "sink")
    return net


@pytest.fixture
def shared_station_config() -> NetworkConfig:
    config = NetworkConfig()
    config.add_source("src1", arrival_rate=0.8, next_node_id="B1")
    config.add_source("src2", arrival_rate=0.2, next_node_id="B2")
    config.add_buffer("B1")
    config.add_buffer("B2")
    config.add_station("Station", service_rate=1.1, c=1)
    config.add_sink("sink")
    config.add_edge("src1", "B1")
    config.add_edge("src2", "B2")
    config.add_edge("B1", "Station")
    config.add_edge("B2", "Station")
    config.add_edge("Station", "sink")
    return config


def test_buffer_enqueue_and_dequeue_records_queue_state():
    net = _network_with_shared_station()
    net.sim.scheduler.schedule(0.0, EventType.ARRIVAL, "B1", _job(1))
    net.sim.step()

    assert net.buffers["B1"].queue_length == 1

    net.sim.step()
    assert net.buffers["B1"].queue_length == 0
    assert net.stations["Station"].busy_servers == 1


def test_station_pulls_from_selected_upstream_buffer():
    net = _network_with_shared_station()
    net.set_station_scheduler("Station", CallbackSchedulingPolicy(lambda _station, _buffers: "B2"))
    net.sim.scheduler.schedule(0.0, EventType.ARRIVAL, "B1", _job(1))
    net.sim.scheduler.schedule(0.0, EventType.ARRIVAL, "B2", _job(2))

    net.sim.step()
    net.sim.step()
    net.sim.step()

    assert net.buffers["B1"].queue_length == 1
    assert net.buffers["B2"].queue_length == 0
    assert net.stations["Station"].busy_servers == 1


def test_empty_buffer_action_falls_through_to_non_empty_buffer():
    net = _network_with_shared_station()
    net.set_station_scheduler("Station", CallbackSchedulingPolicy(lambda _station, _buffers: "B1"))
    net.sim.scheduler.schedule(0.0, EventType.ARRIVAL, "B2", _job(1))

    net.sim.step()
    net.sim.step()

    assert net.buffers["B1"].queue_length == 0
    assert net.buffers["B2"].queue_length == 0
    assert net.stations["Station"].busy_servers == 1


def test_station_with_multiple_servers_fills_idle_capacity():
    net = _network_with_shared_station(c=2)
    net.sim.scheduler.schedule(0.0, EventType.ARRIVAL, "B1", _job(1))
    net.sim.scheduler.schedule(0.0, EventType.ARRIVAL, "B1", _job(2))

    for _ in range(4):
        net.sim.step()

    assert net.buffers["B1"].queue_length == 0
    assert net.stations["Station"].busy_servers == 2


def test_station_departure_reaches_successor_sink():
    net = _network_with_shared_station()
    net.sim.scheduler.schedule(0.0, EventType.ARRIVAL, "B1", _job(1))

    for _ in range(4):
        net.sim.step()

    assert net.stations["Station"].completed_jobs == 1
    assert net._sinks["sink"].count == 1


def test_scheduling_decision_is_not_duplicated_while_pending():
    net = _network_with_shared_station()
    net.sim.scheduler.schedule(0.0, EventType.ARRIVAL, "B1", _job(1))
    net.sim.scheduler.schedule(0.0, EventType.ARRIVAL, "B1", _job(2))

    net.sim.step()
    net.sim.step()

    pending = [
        event for event in net.sim.scheduler._heap
        if event.type == EventType.SCHEDULING_DECISION and event.target_id == "Station"
    ]
    assert len(pending) == 1


def test_legacy_server_model_still_observes_only_servers():
    config = NetworkConfig()
    config.add_source("src", arrival_rate=0.5, next_node_id="srv")
    config.add_server("srv", service_rate=1.0)
    config.add_sink("sink")
    config.add_edge("src", "srv")
    config.add_edge("srv", "sink")
    net = QueueingNetwork.from_config(config)
    assert set(net.observe().keys()) == {"srv"}
    assert net.observe_system()["buffers"] == {}
    assert net.observe_system()["stations"] == {}


def test_validation_rejects_station_without_incoming_buffer():
    net = QueueingNetwork()
    net.add_station("Station", service_rate=1.0)
    net.add_sink("sink")
    net.add_edge("Station", "sink")

    with pytest.raises(ValueError, match="incoming buffer"):
        net.validate()


def test_validation_rejects_station_with_multiple_outgoing_edges():
    net = QueueingNetwork()
    net.add_source("src", arrival_rate=0.5, next_node_id="B1")
    net.add_buffer("B1")
    net.add_station("Station", service_rate=1.0)
    net.add_sink("sink1")
    net.add_sink("sink2")
    net.add_edge("src", "B1")
    net.add_edge("B1", "Station")
    net.add_edge("Station", "sink1")
    net.add_edge("Station", "sink2")

    with pytest.raises(ValueError, match="exactly one outgoing edge"):
        net.validate()


def test_validation_rejects_non_buffer_station_predecessor():
    net = QueueingNetwork()
    net.add_source("src", arrival_rate=0.5, next_node_id="Station")
    net.add_station("Station", service_rate=1.0)
    net.add_sink("sink")
    net.add_edge("src", "Station")
    net.add_edge("Station", "sink")

    with pytest.raises(ValueError, match="receive work from buffers"):
        net.validate()


def test_validation_rejects_buffer_successor_that_is_not_station():
    net = QueueingNetwork()
    net.add_source("src", arrival_rate=0.5, next_node_id="B1")
    net.add_buffer("B1")
    net.add_sink("sink")
    net.add_edge("src", "B1")
    net.add_edge("B1", "sink")

    with pytest.raises(ValueError, match="only connect to station"):
        net.validate()


def test_validation_accepts_legacy_topology():
    config = NetworkConfig()
    config.add_source("src", arrival_rate=0.8, next_node_id="srv")
    config.add_server("srv", service_rate=1.0)
    config.add_sink("sink")
    config.add_edge("src", "srv")
    config.add_edge("srv", "sink")
    QueueingNetwork.from_config(config).validate()


class TestSharedStationSchedulingGym:
    def test_spaces(self, shared_station_config):
        env = SharedStationSchedulingGym(shared_station_config, control_station_id="Station", max_steps=100)
        assert env.observation_space.shape == (3,)
        assert env.action_space.n == 2

    def test_reset_observation_is_zero(self, shared_station_config):
        env = SharedStationSchedulingGym(shared_station_config, control_station_id="Station", max_steps=100)
        obs, _ = env.reset(seed=1)
        assert np.all(obs == 0)

    def test_action_zero_prefers_first_buffer(self, shared_station_config):
        random.seed(2)
        env = SharedStationSchedulingGym(shared_station_config, control_station_id="Station", max_steps=150)
        env.reset(seed=2)

        b1_total = 0.0
        b2_total = 0.0
        for _ in range(80):
            obs, _, terminated, truncated, _ = env.step(0)
            b1_total += obs[0]
            b2_total += obs[1]
            if terminated or truncated:
                break

        assert b1_total < b2_total

    def test_action_one_prefers_second_buffer(self, shared_station_config):
        random.seed(2)
        env = SharedStationSchedulingGym(shared_station_config, control_station_id="Station", max_steps=150)
        env.reset(seed=2)

        b1_total = 0.0
        b2_total = 0.0
        for _ in range(80):
            obs, _, terminated, truncated, _ = env.step(1)
            b1_total += obs[0]
            b2_total += obs[1]
            if terminated or truncated:
                break

        assert b2_total < b1_total

    def test_invalid_action_wraps_via_modulo(self, shared_station_config):
        random.seed(3)
        env = SharedStationSchedulingGym(shared_station_config, control_station_id="Station", max_steps=20)
        env.reset(seed=3)
        _, _, _, _, _ = env.step(3)
        assert env._pending_action == 3

    def test_step_advances_to_control_station_decision_epoch(self, shared_station_config):
        env = SharedStationSchedulingGym(shared_station_config, control_station_id="Station", max_steps=20)
        env.reset(seed=4)
        _, _, _, _, _ = env.step(0)
        assert env._last_event_time == env._network.sim.clock
        assert env._network.stations["Station"].busy_servers == 1

    def test_reward_matches_total_buffer_queue_length_times_dt(self, shared_station_config):
        random.seed(5)
        env = SharedStationSchedulingGym(shared_station_config, control_station_id="Station", max_steps=100)
        env.reset(seed=5)

        for _ in range(10):
            _, _, terminated, truncated, _ = env.step(0)
            if terminated or truncated:
                break

        previous_time = env._last_event_time
        _, reward, _, _, _ = env.step(0)
        dt = env._last_event_time - previous_time
        total_queue = sum(buffer.queue_length for buffer in env._network.buffers.values())
        assert reward == pytest.approx(-total_queue * dt)

    def test_alternating_policy_reduces_queue_imbalance(self):
        config = NetworkConfig()
        config.add_source("src1", arrival_rate=2.0, next_node_id="B1")
        config.add_source("src2", arrival_rate=2.0, next_node_id="B2")
        config.add_buffer("B1")
        config.add_buffer("B2")
        config.add_station("Station", service_rate=0.5, c=1)
        config.add_sink("sink")
        config.add_edge("src1", "B1")
        config.add_edge("src2", "B2")
        config.add_edge("B1", "Station")
        config.add_edge("B2", "Station")
        config.add_edge("Station", "sink")

        def run_episode(action_fn, seed):
            random.seed(seed)
            env = SharedStationSchedulingGym(config, control_station_id="Station", max_steps=80)
            env.reset(seed=seed)
            b1_total = 0.0
            b2_total = 0.0
            terminated = truncated = False
            step = 0
            while not (terminated or truncated):
                obs, _, terminated, truncated, _ = env.step(action_fn(step))
                b1_total += obs[0]
                b2_total += obs[1]
                step += 1
            return abs(b1_total - b2_total)

        fixed_gap = run_episode(lambda _step: 0, seed=7)
        alternating_gap = run_episode(lambda step: step % 2, seed=7)
        assert alternating_gap < fixed_gap

    def test_check_env(self, shared_station_config):
        check_env(SharedStationSchedulingGym(shared_station_config, control_station_id="Station", max_steps=50), warn=True)
