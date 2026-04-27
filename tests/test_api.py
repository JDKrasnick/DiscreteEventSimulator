from fastapi.testclient import TestClient

from api.main import app


def _mm1_config() -> dict:
    return {
        "warm_up_time": 0.0,
        "nodes": [
            {"id": "src", "type": "source", "arrival_rate": 0.8, "next_node_id": "srv"},
            {"id": "srv", "type": "server", "service_rate": 1.0, "c": 1},
            {"id": "snk", "type": "sink"},
        ],
        "edges": [
            {"source": "src", "target": "srv", "weight": 1.0},
            {"source": "srv", "target": "snk", "weight": 1.0},
        ],
        "default_router": {"type": "probabilistic"},
    }


def _shared_station_config() -> dict:
    return {
        "warm_up_time": 0.0,
        "nodes": [
            {"id": "src1", "type": "source", "arrival_rate": 0.8, "next_node_id": "B1"},
            {"id": "src2", "type": "source", "arrival_rate": 0.2, "next_node_id": "B2"},
            {"id": "B1", "type": "buffer"},
            {"id": "B2", "type": "buffer"},
            {"id": "Station", "type": "station", "service_rate": 1.1, "c": 1, "scheduler": {"type": "longest_queue"}},
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
    }


def test_step_can_be_called_repeatedly():
    client = TestClient(app)

    create = client.post("/api/networks", json=_mm1_config())
    assert create.status_code == 201
    session_id = create.json()["id"]

    first = client.post(f"/api/networks/{session_id}/step")
    assert first.status_code == 200
    assert first.json()["state"]["status"] == "paused"

    second = client.post(f"/api/networks/{session_id}/step")
    assert second.status_code == 200
    assert second.json()["state"]["event_count"] == 2
    assert second.json()["state"]["status"] == "paused"


def test_stop_transitions_running_session_out_of_running_state():
    client = TestClient(app)

    create = client.post("/api/networks", json=_mm1_config())
    assert create.status_code == 201
    session_id = create.json()["id"]

    with client.websocket_connect(f"/api/networks/{session_id}/stream") as websocket:
        websocket.send_json({"until": 1_000_000_000, "stream_interval": 0.05})
        first_message = websocket.receive_json()
        assert first_message["type"] == "state"

        stop = client.post(f"/api/networks/{session_id}/stop")
        assert stop.status_code == 200
        assert stop.json()["status"] == "paused"

        terminal_type = None
        for _ in range(10):
            message = websocket.receive_json()
            terminal_type = message["type"]
            if terminal_type == "stopped":
                break
        assert terminal_type == "stopped"

    state = client.get(f"/api/networks/{session_id}/state")
    assert state.status_code == 200
    assert state.json()["status"] == "paused"


def test_shared_station_network_round_trips_and_returns_additive_state():
    client = TestClient(app)

    create = client.post("/api/networks", json=_shared_station_config())
    assert create.status_code == 201
    session_id = create.json()["id"]

    network = client.get(f"/api/networks/{session_id}")
    assert network.status_code == 200
    node_kinds = {node["kind"] for node in network.json()["nodes"]}
    assert {"buffer", "station"} <= node_kinds

    stepped = client.post(f"/api/networks/{session_id}/step")
    assert stepped.status_code == 200
    state = stepped.json()["state"]
    assert "servers" in state
    assert "buffers" in state
    assert "stations" in state

    stats = stepped.json()["stats"]
    assert any(row["node_kind"] == "buffer" for row in stats)
