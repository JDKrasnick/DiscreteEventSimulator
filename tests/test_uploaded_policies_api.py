from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.policy_registry import registry


PLUGIN_SOURCE = """
from des.network.routing import RoutingPolicy
from des.network.scheduling import SchedulingPolicy
from des.network.server_queue import ServerQueuePolicy


class SecondSuccessorRouter(RoutingPolicy):
    '''Always routes to the last available downstream node.'''
    def next_node(self, customer, successors):
        return successors[-1][0]


class LastJobQueuePolicy(ServerQueuePolicy):
    '''Always starts the newest waiting job next.'''
    def choose_job(self, server, jobs):
        return len(jobs) - 1


class LastBufferScheduler(SchedulingPolicy):
    '''Always asks the station to start from the last upstream buffer.'''
    def choose_buffer(self, station, buffers):
        return len(buffers) - 1


ROUTERS = {"second_successor": SecondSuccessorRouter}
SERVER_QUEUE_POLICIES = {"last_job": LastJobQueuePolicy}
STATION_SCHEDULERS = {"last_buffer": LastBufferScheduler}
"""


@pytest.fixture
def isolated_policy_registry(tmp_path: Path):
    original_dir = registry._storage_dir
    registry.set_storage_dir(tmp_path)
    try:
        yield tmp_path
    finally:
        registry.set_storage_dir(original_dir)


def test_policy_upload_lists_grouped_policies(isolated_policy_registry):
    client = TestClient(app)

    upload = client.post(
        "/api/policies/upload",
        files={"file": ("custom_policies.py", PLUGIN_SOURCE.encode("utf-8"), "text/x-python")},
    )
    assert upload.status_code == 201

    listed = client.get("/api/policies")
    assert listed.status_code == 200
    payload = listed.json()

    assert payload["server_routing"][0]["name"] == "second_successor"
    assert payload["server_queue"][0]["name"] == "last_job"
    assert payload["station_scheduling"][0]["name"] == "last_buffer"


def test_uploaded_server_policies_can_be_selected_in_network_config(isolated_policy_registry):
    client = TestClient(app)
    client.post(
        "/api/policies/upload",
        files={"file": ("custom_policies.py", PLUGIN_SOURCE.encode("utf-8"), "text/x-python")},
    )

    create = client.post(
        "/api/networks",
        json={
            "warm_up_time": 0.0,
            "nodes": [
                {"id": "src", "type": "source", "arrival_rate": 0.8, "next_node_id": "srv"},
                {"id": "srv", "type": "server", "service_rate": 1.0, "c": 1,
                 "queue_policy": {"type": "custom", "policy_id": "custom_policies:server_queue:last_job"},
                 "router": {"type": "custom", "policy_id": "custom_policies:server_router:second_successor"}},
                {"id": "sink_a", "type": "sink"},
                {"id": "sink_b", "type": "sink"},
            ],
            "edges": [
                {"source": "src", "target": "srv", "weight": 1.0},
                {"source": "srv", "target": "sink_a", "weight": 1.0},
                {"source": "srv", "target": "sink_b", "weight": 1.0},
            ],
            "default_router": {"type": "probabilistic"},
        },
    )
    assert create.status_code == 201

    session_id = create.json()["id"]
    network = client.get(f"/api/networks/{session_id}")
    assert network.status_code == 200
    server = next(node for node in network.json()["nodes"] if node["id"] == "srv")
    assert server["router"]["policy_id"] == "custom_policies:server_router:second_successor"
    assert server["queue_policy"]["policy_id"] == "custom_policies:server_queue:last_job"


def test_uploaded_station_scheduler_can_be_selected_in_network_config(isolated_policy_registry):
    client = TestClient(app)
    client.post(
        "/api/policies/upload",
        files={"file": ("custom_policies.py", PLUGIN_SOURCE.encode("utf-8"), "text/x-python")},
    )

    create = client.post(
        "/api/networks",
        json={
            "warm_up_time": 0.0,
            "nodes": [
                {"id": "src1", "type": "source", "arrival_rate": 0.8, "next_node_id": "B1"},
                {"id": "src2", "type": "source", "arrival_rate": 0.2, "next_node_id": "B2"},
                {"id": "B1", "type": "buffer"},
                {"id": "B2", "type": "buffer"},
                {"id": "Station", "type": "station", "service_rate": 1.0, "c": 1,
                 "scheduler": {"type": "custom", "policy_id": "custom_policies:station_scheduler:last_buffer"}},
                {"id": "sink", "type": "sink"},
            ],
            "edges": [
                {"source": "src1", "target": "B1", "weight": 1.0},
                {"source": "src2", "target": "B2", "weight": 1.0},
                {"source": "B1", "target": "Station", "weight": 1.0},
                {"source": "B2", "target": "Station", "weight": 1.0},
                {"source": "Station", "target": "sink", "weight": 1.0},
            ],
            "default_router": {"type": "probabilistic"},
        },
    )
    assert create.status_code == 201

    session_id = create.json()["id"]
    network = client.get(f"/api/networks/{session_id}")
    assert network.status_code == 200
    station = next(node for node in network.json()["nodes"] if node["id"] == "Station")
    assert station["scheduler"]["policy_id"] == "custom_policies:station_scheduler:last_buffer"


def test_invalid_uploaded_policy_file_is_rejected(isolated_policy_registry):
    client = TestClient(app)

    upload = client.post(
        "/api/policies/upload",
        files={"file": ("bad_policy.py", b"ROUTERS = {'bad': object()}\n", "text/x-python")},
    )
    assert upload.status_code == 422
    assert "zero-argument class or factory function" in upload.json()["detail"]
