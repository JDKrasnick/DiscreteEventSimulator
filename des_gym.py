import gymnasium as gym
from gymnasium import spaces
import numpy as np

from des.engine.event import EventType
from des.network import CallbackRouter, NetworkConfig, QueueingNetwork


class DiscreteEventGym(gym.Env):
    def __init__(self, config: NetworkConfig, max_steps: int):
        super().__init__()
        self._config = config
        self._max_steps = max_steps
        n = len(config.servers)
        self.observation_space = spaces.Box(low=0, high=np.inf, shape=(n * 2,), dtype=np.float32)
        self.action_space = spaces.Discrete(n)
        self._network: QueueingNetwork | None = None
        self._pending_action: int = 0
        self._last_event_time: float = 0.0
        self._steps: int = 0

    def _get_obs(self) -> np.ndarray:
        assert self._network is not None
        flat = []
        for state in self._network.observe().values():
            flat.append(float(state["queue_length"]))
            flat.append(float(state["busy_servers"]))
        return np.array(flat, dtype=np.float32)

    def _get_reward(self, dt: float) -> float:
        # This is an SMDP (semi-MDP): decision epochs are event times, not
        # fixed clock ticks, so the sojourn time between decisions varies.
        # Weighting by dt gives the time-average queue length objective
        # instead of a per-event count, which is the correct cost for
        # queueing control (e.g. minimising mean number in system).
        assert self._network is not None
        return -sum(s["queue_length"] for s in self._network.observe().values()) * dt

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._network = QueueingNetwork.from_config(self._config)
        self._network.set_router(
            CallbackRouter(lambda _c, succs: succs[self._pending_action % len(succs)][0])
        )
        self._pending_action = 0
        self._last_event_time = 0.0
        self._steps = 0
        self._network.start()
        return self._get_obs(), {}

    def step(self, action: int):
        assert self._network is not None
        self._pending_action = action

        # Advance until the next departure, which is when routing fires.
        # Arrival events don't involve a routing decision so we skip them.
        event = self._network.sim.step()
        while event is not None and event.type != EventType.DEPARTURE:
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
