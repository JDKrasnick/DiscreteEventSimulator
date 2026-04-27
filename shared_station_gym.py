import gymnasium as gym
from gymnasium import spaces
import numpy as np

from des.engine.event import EventType
from des.network import CallbackSchedulingPolicy, NetworkConfig, QueueingNetwork


class SharedStationSchedulingGym(gym.Env):
    def __init__(self, config: NetworkConfig, control_station_id: str, max_steps: int):
        super().__init__()
        self._config = config
        self._control_station_id = control_station_id
        self._max_steps = max_steps

        n_buffers = len(config.buffers)
        n_stations = len(config.stations)
        controlled = next((s for s in config.stations if s.node_id == control_station_id), None)
        if controlled is None:
            raise ValueError(f"Unknown control station '{control_station_id}'")

        self._control_buffer_ids = [
            buf.node_id
            for buf in config.buffers
            if (buf.node_id, control_station_id) in config.edges
        ]
        if not self._control_buffer_ids:
            raise ValueError(f"Station '{control_station_id}' has no upstream buffers in config")

        self.observation_space = spaces.Box(
            low=0,
            high=np.inf,
            shape=(n_buffers + n_stations,),
            dtype=np.float32,
        )
        self.action_space = spaces.Discrete(len(self._control_buffer_ids))
        self._network: QueueingNetwork | None = None
        self._pending_action = 0
        self._last_event_time = 0.0
        self._steps = 0

    def _get_obs(self) -> np.ndarray:
        assert self._network is not None
        flat = []
        for buffer in self._network.buffers.values():
            flat.append(float(buffer.queue_length))
        for station in self._network.stations.values():
            flat.append(float(station.busy_servers))
        return np.array(flat, dtype=np.float32)

    def _get_reward(self, dt: float) -> float:
        assert self._network is not None
        total_queue = sum(buffer.queue_length for buffer in self._network.buffers.values())
        return -total_queue * dt

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._network = QueueingNetwork.from_config(self._config)
        self._network.set_station_scheduler(
            self._control_station_id,
            CallbackSchedulingPolicy(
                lambda _station, buffers: self._control_buffer_ids[
                    self._pending_action % len(self._control_buffer_ids)
                ]
            ),
        )
        self._pending_action = 0
        self._last_event_time = 0.0
        self._steps = 0
        self._network.start()
        return self._get_obs(), {}

    def step(self, action: int):
        assert self._network is not None
        self._pending_action = action

        event = self._network.sim.step()
        while event is not None and not (
            event.type == EventType.SCHEDULING_DECISION
            and event.target_id == self._control_station_id
        ):
            event = self._network.sim.step()

        now = self._network.sim.clock
        dt = now - self._last_event_time
        self._last_event_time = now

        self._steps += 1
        obs = self._get_obs()
        reward = self._get_reward(dt)
        terminated = self._network.sim.scheduler.is_empty()
        truncated = self._steps >= self._max_steps
        info = {}
        if terminated or truncated:
            info["episode_stats"] = self._network.stats()
        return obs, reward, terminated, truncated, info

    def render(self, mode="human"):
        pass

    def close(self):
        pass
