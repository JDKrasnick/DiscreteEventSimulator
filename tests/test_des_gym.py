"""
Unit tests for DiscreteEventGym (des_gym.py).

Coverage areas:
  1. Gymnasium API compliance  - spaces, reset/step signatures, dtypes
  2. Observation validity      - shape, bounds, dtype
  3. Reward semantics          - always ≤ 0, matches network state
  4. Termination flags         - terminated fires correctly, truncated always False
  5. Reset idempotency         - multiple resets, seed param, state cleared
  6. Routing action semantics  - action selects successor, modulo wraps
  7. RL integration            - full episode loop, check_env, action effect on load
"""
import random

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from des.network import NetworkConfig
from des_gym import DiscreteEventGym


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def single_server_config() -> NetworkConfig:
    """source → S1 → sink.  One server: action space Discrete(1)."""
    config = NetworkConfig()
    config.add_source("source", arrival_rate=0.5, next_node_id="S1")
    config.add_server("S1", service_rate=1.0)
    config.add_sink("sink")
    config.add_edge("source", "S1")
    config.add_edge("S1", "sink")
    return config


@pytest.fixture
def two_server_config() -> NetworkConfig:
    """
    source → dispatcher(fast) → S1 or S2 → sink.

    The dispatcher is the routing decision point: its two successors are S1
    and S2, so the RL action selects which backend server receives each
    customer.  Total servers = 3, so action_space = Discrete(3) and
    observation shape = (6,).

    Obs layout (insertion order preserved by Python dicts):
      [0] dispatcher queue_length   [1] dispatcher busy_servers
      [2] S1 queue_length           [3] S1 busy_servers
      [4] S2 queue_length           [5] S2 busy_servers
    """
    config = NetworkConfig()
    config.add_source("source", arrival_rate=1.4, next_node_id="dispatcher")
    config.add_server("dispatcher", service_rate=20.0)
    config.add_server("S1", service_rate=1.0)
    config.add_server("S2", service_rate=1.0)
    config.add_sink("sink")
    config.add_edge("source", "dispatcher")
    config.add_edge("dispatcher", "S1")
    config.add_edge("dispatcher", "S2")
    config.add_edge("S1", "sink")
    config.add_edge("S2", "sink")
    return config


@pytest.fixture
def env(two_server_config) -> DiscreteEventGym:
    e = DiscreteEventGym(two_server_config, max_steps=500)
    random.seed(42)
    e.reset(seed=42)
    return e


# ---------------------------------------------------------------------------
# 1. Gymnasium API compliance
# ---------------------------------------------------------------------------

class TestSpaces:
    def test_obs_space_shape_single_server(self, single_server_config):
        assert DiscreteEventGym(single_server_config, max_steps=500).observation_space.shape == (2,)

    def test_obs_space_shape_two_server(self, two_server_config):
        assert DiscreteEventGym(two_server_config, max_steps=500).observation_space.shape == (6,)

    def test_obs_space_dtype(self, two_server_config):
        assert DiscreteEventGym(two_server_config, max_steps=500).observation_space.dtype == np.float32

    def test_obs_space_lower_bound_zero(self, two_server_config):
        lb = DiscreteEventGym(two_server_config, max_steps=500).observation_space.low
        assert np.all(lb == 0)

    def test_action_space_single_server(self, single_server_config):
        assert DiscreteEventGym(single_server_config, max_steps=500).action_space.n == 1

    def test_action_space_two_server(self, two_server_config):
        assert DiscreteEventGym(two_server_config, max_steps=500).action_space.n == 3


class TestResetSignature:
    def test_reset_returns_two_tuple(self, two_server_config):
        result = DiscreteEventGym(two_server_config, max_steps=500).reset()
        assert isinstance(result, tuple) and len(result) == 2

    def test_reset_obs_is_ndarray(self, two_server_config):
        obs, _ = DiscreteEventGym(two_server_config, max_steps=500).reset()
        assert isinstance(obs, np.ndarray)

    def test_reset_info_is_dict(self, two_server_config):
        _, info = DiscreteEventGym(two_server_config, max_steps=500).reset()
        assert isinstance(info, dict)

    def test_reset_obs_shape(self, two_server_config):
        obs, _ = DiscreteEventGym(two_server_config, max_steps=500).reset()
        assert obs.shape == (6,)

    def test_reset_obs_dtype(self, two_server_config):
        obs, _ = DiscreteEventGym(two_server_config, max_steps=500).reset()
        assert obs.dtype == np.float32

    def test_reset_accepts_seed(self, two_server_config):
        obs, _ = DiscreteEventGym(two_server_config, max_steps=500).reset(seed=99)
        assert obs.shape == (6,)


class TestStepSignature:
    def test_step_returns_five_tuple(self, env):
        assert len(env.step(0)) == 5

    def test_step_obs_is_ndarray(self, env):
        obs, *_ = env.step(0)
        assert isinstance(obs, np.ndarray)

    def test_step_reward_is_float(self, env):
        _, reward, *_ = env.step(0)
        assert isinstance(reward, (float, int, np.floating))

    def test_step_terminated_is_bool(self, env):
        _, _, terminated, *_ = env.step(0)
        assert isinstance(terminated, bool)

    def test_step_truncated_is_bool(self, env):
        _, _, _, truncated, _ = env.step(0)
        assert isinstance(truncated, bool)

    def test_step_info_is_dict(self, env):
        *_, info = env.step(0)
        assert isinstance(info, dict)


# ---------------------------------------------------------------------------
# 2. Observation validity
# ---------------------------------------------------------------------------

class TestObservation:
    def test_initial_obs_all_zero(self, two_server_config):
        """No events processed at reset time, so all servers start idle."""
        obs, _ = DiscreteEventGym(two_server_config, max_steps=500).reset()
        assert np.all(obs == 0)

    def test_reset_obs_in_observation_space(self, two_server_config):
        env = DiscreteEventGym(two_server_config, max_steps=500)
        obs, _ = env.reset()
        assert env.observation_space.contains(obs)

    def test_obs_non_negative_after_reset(self, two_server_config):
        obs, _ = DiscreteEventGym(two_server_config, max_steps=500).reset()
        assert np.all(obs >= 0)

    def test_obs_non_negative_during_episode(self, env):
        for _ in range(50):
            obs, _, terminated, _, _ = env.step(0)
            assert np.all(obs >= 0)
            if terminated:
                break

    def test_step_obs_shape_unchanged(self, env):
        obs, _, _, _, _ = env.step(0)
        assert obs.shape == (6,)

    def test_step_obs_in_observation_space(self, env):
        for _ in range(20):
            obs, _, terminated, _, _ = env.step(0)
            assert env.observation_space.contains(obs)
            if terminated:
                break

    def test_obs_dtype_after_step(self, env):
        obs, *_ = env.step(0)
        assert obs.dtype == np.float32


# ---------------------------------------------------------------------------
# 3. Reward semantics
# ---------------------------------------------------------------------------

class TestReward:
    def test_reward_non_positive_throughout_episode(self, env):
        for _ in range(50):
            _, reward, terminated, _, _ = env.step(0)
            assert reward <= 0
            if terminated:
                break

    def test_reward_equals_negative_queue_sum_times_dt(self, env):
        # Warm up until at least one server has a non-empty queue so dt != 0
        # matters and we actually test the weighting.
        for _ in range(30):
            _, _, terminated, truncated, _ = env.step(0)
            if terminated or truncated:
                break
        queue_sum = sum(s["queue_length"] for s in env._network.observe().values())
        assert queue_sum > 0, "queue never built up — test setup invalid"

        prev_time = env._last_event_time
        _, reward, _, _, _ = env.step(0)
        dt = env._last_event_time - prev_time
        queue_sum = sum(s["queue_length"] for s in env._network.observe().values())
        assert reward == pytest.approx(-queue_sum * dt)

    def test_reward_zero_when_queues_empty(self):
        """Very fast service + slow arrivals keeps queues at 0."""
        random.seed(0)
        config = NetworkConfig()
        config.add_source("source", arrival_rate=0.01, next_node_id="S1")
        config.add_server("S1", service_rate=1000.0)
        config.add_sink("sink")
        config.add_edge("source", "S1")
        config.add_edge("S1", "sink")

        e = DiscreteEventGym(config, max_steps=500)
        e.reset(seed=0)
        _, reward, _, _, _ = e.step(0)
        assert reward == 0.0


# ---------------------------------------------------------------------------
# 4. Termination flags
# ---------------------------------------------------------------------------

class TestTermination:
    def test_terminated_false_with_continuous_source(self, two_server_config):
        """
        A Poisson source re-schedules the next arrival on every handle() call,
        so the scheduler is never empty and terminated stays False throughout
        normal operation.  TimeLimit wrapper is the right mechanism for
        finite-length episodes.
        """
        env = DiscreteEventGym(two_server_config, max_steps=500)
        env.reset(seed=7)
        for _ in range(200):
            _, _, terminated, _, _ = env.step(0)
            assert not terminated

    def test_terminated_true_when_scheduler_is_empty(self, two_server_config):
        """
        terminated mirrors scheduler.is_empty().  Verify they agree on every
        step; we never expect it to fire naturally (see test above), but the
        flag must be accurate.
        """
        env = DiscreteEventGym(two_server_config, max_steps=500)
        env.reset(seed=7)
        for _ in range(100):
            _, _, terminated, _, _ = env.step(0)
            assert terminated == env._network.sim.scheduler.is_empty()

    def test_truncated_always_false(self, two_server_config):
        env = DiscreteEventGym(two_server_config, max_steps=500)
        env.reset(seed=7)
        for _ in range(200):
            _, _, _, truncated, _ = env.step(0)
            assert truncated is False


# ---------------------------------------------------------------------------
# 5. Reset idempotency
# ---------------------------------------------------------------------------

class TestReset:
    def test_multiple_resets_succeed(self, two_server_config):
        env = DiscreteEventGym(two_server_config, max_steps=500)
        for seed in range(5):
            obs, info = env.reset(seed=seed)
            assert obs.shape == (6,)
            assert isinstance(info, dict)

    def test_reset_clears_pending_action(self, two_server_config):
        env = DiscreteEventGym(two_server_config, max_steps=500)
        env.reset()
        env.step(2)
        assert env._pending_action == 2
        env.reset()
        assert env._pending_action == 0

    def test_reset_creates_fresh_network(self, two_server_config):
        env = DiscreteEventGym(two_server_config, max_steps=500)
        env.reset()
        net_before = env._network
        env.reset()
        assert env._network is not net_before

    def test_reset_restores_zero_obs_after_episode(self, two_server_config):
        env = DiscreteEventGym(two_server_config, max_steps=500)
        env.reset()
        for _ in range(20):
            _, _, terminated, _, _ = env.step(0)
            if terminated:
                break
        obs, _ = env.reset()
        assert np.all(obs == 0)

    def test_reset_network_is_none_before_first_reset(self, two_server_config):
        env = DiscreteEventGym(two_server_config, max_steps=500)
        assert env._network is None


# ---------------------------------------------------------------------------
# 6. Routing action semantics
# ---------------------------------------------------------------------------

class TestRoutingSemantics:
    def test_action_zero_loads_s1_only(self, two_server_config):
        """Action 0 → succs[0 % 2] = S1.  S2 should receive no customers."""
        random.seed(0)
        env = DiscreteEventGym(two_server_config, max_steps=500)
        env.reset(seed=0)

        s1_total = s2_total = 0
        for _ in range(150):
            obs, _, terminated, _, _ = env.step(0)
            s1_total += obs[2] + obs[3]
            s2_total += obs[4] + obs[5]
            if terminated:
                break

        assert s1_total > 0
        assert s2_total == 0

    def test_action_one_loads_s2_only(self, two_server_config):
        """Action 1 → succs[1 % 2] = S2.  S1 should receive no customers."""
        random.seed(0)
        env = DiscreteEventGym(two_server_config, max_steps=500)
        env.reset(seed=0)

        s1_total = s2_total = 0
        for _ in range(150):
            obs, _, terminated, _, _ = env.step(1)
            s1_total += obs[2] + obs[3]
            s2_total += obs[4] + obs[5]
            if terminated:
                break

        assert s2_total > 0
        assert s1_total == 0

    def test_action_modulo_wraps_to_s1(self, two_server_config):
        """Action 2 wraps: 2 % 2 == 0 → S1.  S2 receives no customers."""
        random.seed(0)
        env = DiscreteEventGym(two_server_config, max_steps=500)
        env.reset(seed=0)

        s1_total = s2_total = 0
        for _ in range(150):
            obs, _, terminated, _, _ = env.step(2)
            s1_total += obs[2] + obs[3]
            s2_total += obs[4] + obs[5]
            if terminated:
                break

        assert s1_total > 0
        assert s2_total == 0

    def test_pending_action_updated_per_step(self, two_server_config):
        env = DiscreteEventGym(two_server_config, max_steps=500)
        env.reset()
        env.step(1)
        assert env._pending_action == 1
        env.step(0)
        assert env._pending_action == 0
        env.step(2)
        assert env._pending_action == 2

    def test_routing_callback_receives_correct_action(self, two_server_config):
        """
        Verify the callback uses _pending_action, not a stale value.

        Each step() may consume multiple events (arrivals at dispatcher, S1
        departures to sink, etc.) before a dispatcher DEPARTURE fires.  So a
        single alternating step may not immediately show S2 load.  Running 200
        steps with strict alternation gives the dispatcher enough departures to
        route to both servers.
        """
        random.seed(3)
        env = DiscreteEventGym(two_server_config, max_steps=500)
        env.reset(seed=3)

        s1_total = s2_total = 0
        for i in range(200):
            obs, _, _, _, _ = env.step(i % 2)
            s1_total += obs[2] + obs[3]
            s2_total += obs[4] + obs[5]

        assert s1_total > 0
        assert s2_total > 0


# ---------------------------------------------------------------------------
# 7. RL integration
# ---------------------------------------------------------------------------

class TestRLIntegration:
    def test_random_policy_completes_episode(self, two_server_config):
        """Random actions should produce a valid, complete episode."""
        random.seed(42)
        env = DiscreteEventGym(two_server_config, max_steps=500)
        obs, _ = env.reset(seed=42)

        assert env.observation_space.contains(obs)
        rewards = []
        terminated = truncated = False
        while not (terminated or truncated):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, _ = env.step(action)
            assert env.observation_space.contains(obs)
            rewards.append(reward)

        assert len(rewards) > 0
        assert all(r <= 0 for r in rewards)

    def test_multiple_episodes_back_to_back(self, two_server_config):
        env = DiscreteEventGym(two_server_config, max_steps=500)
        for episode in range(3):
            obs, _ = env.reset(seed=episode)
            assert np.all(obs == 0)
            terminated = truncated = False
            while not (terminated or truncated):
                _, _, terminated, truncated, _ = env.step(episode % 2)

    def test_fixed_routing_produces_load_imbalance(self, two_server_config):
        """Always action=0 should leave S2 completely idle."""
        random.seed(1)
        env = DiscreteEventGym(two_server_config, max_steps=500)
        env.reset(seed=1)
        s2_total = 0.0
        terminated = truncated = False
        while not (terminated or truncated):
            obs, _, terminated, truncated, _ = env.step(0)
            s2_total += obs[4] + obs[5]
        assert s2_total == 0.0

    def test_balanced_routing_outperforms_fixed(self, two_server_config):
        """
        Alternating between S1 and S2 (balanced) vs always S1 (overloaded).
        With arrival_rate=1.4 and mu=1.0 each, always-to-one causes rho=1.4
        which is unstable; balanced gives rho=0.7 each.  Cumulative reward
        for balanced should be strictly higher (less total queue time).
        """
        def run_episode(action_fn, seed):
            random.seed(seed)
            env = DiscreteEventGym(two_server_config, max_steps=500)
            env.reset(seed=seed)
            total = 0.0
            terminated = truncated = False
            step = 0
            while not (terminated or truncated):
                _, reward, terminated, truncated, _ = env.step(action_fn(step))
                total += reward
                step += 1
            return total

        reward_balanced = run_episode(lambda s: s % 2, seed=5)
        reward_fixed    = run_episode(lambda _: 0,     seed=5)

        assert reward_balanced > reward_fixed

    def test_check_env(self, two_server_config):
        """gymnasium's own checker validates the full API contract."""
        check_env(DiscreteEventGym(two_server_config, max_steps=500), warn=True)
