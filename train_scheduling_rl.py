"""
REINFORCE on SharedStationSchedulingGym.

Network:
    src_fast (λ=0.9) -> B1 \
                             -> SharedStation (μ=1.5) -> sink
    src_slow (λ=0.4) -> B2 /

The agent decides which upstream buffer the shared station should serve next.

Run:
    python3 train_scheduling_rl.py
"""

import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from des.network import NetworkConfig
from shared_station_gym import SharedStationSchedulingGym


def make_env(max_steps: int = 500) -> SharedStationSchedulingGym:
    config = NetworkConfig()
    config.add_source("src_fast", arrival_rate=0.9, next_node_id="B1")
    config.add_source("src_slow", arrival_rate=0.4, next_node_id="B2")
    config.add_buffer("B1")
    config.add_buffer("B2")
    config.add_station("SharedStation", service_rate=1.5, c=1)
    config.add_sink("sink")
    config.add_edge("src_fast", "B1")
    config.add_edge("src_slow", "B2")
    config.add_edge("B1", "SharedStation")
    config.add_edge("B2", "SharedStation")
    config.add_edge("SharedStation", "sink")
    return SharedStationSchedulingGym(config, control_station_id="SharedStation", max_steps=max_steps)


class Policy(nn.Module):
    def __init__(self, obs_dim: int, n_actions: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim, 64),
            nn.Tanh(),
            nn.Linear(64, 64),
            nn.Tanh(),
            nn.Linear(64, n_actions),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.softmax(self.net(x), dim=-1)


def run_episode(
    env: SharedStationSchedulingGym, policy: Policy
) -> tuple[list[torch.Tensor], list[float], list[dict]]:
    obs, _ = env.reset()
    log_probs: list[torch.Tensor] = []
    rewards: list[float] = []
    episode_stats: list[dict] = []
    done = False
    while not done:
        obs_t = torch.tensor(obs, dtype=torch.float32)
        probs = policy(obs_t)
        dist = torch.distributions.Categorical(probs)
        action = dist.sample()
        log_probs.append(dist.log_prob(action))
        obs, reward, terminated, truncated, info = env.step(action.item())
        rewards.append(reward)
        done = terminated or truncated
        if "episode_stats" in info:
            episode_stats = info["episode_stats"]
    return log_probs, rewards, episode_stats


def compute_returns(rewards: list[float], gamma: float = 0.99) -> list[float]:
    returns: list[float] = []
    total = 0.0
    for reward in reversed(rewards):
        total = reward + gamma * total
        returns.insert(0, total)
    return returns


def train(
    n_episodes: int = 400,
    gamma: float = 0.99,
    lr: float = 1e-3,
    max_steps: int = 500,
    log_every: int = 50,
    batch_size: int = 8,
    baseline_alpha: float = 0.05,
) -> tuple[list[float], list[float]]:
    env = make_env(max_steps)
    obs_dim = env.observation_space.shape[0]
    n_actions = env.action_space.n

    policy = Policy(obs_dim, n_actions)
    optimizer = optim.Adam(policy.parameters(), lr=lr)

    running_mean = 0.0
    running_var = 1.0
    episode_returns: list[float] = []
    losses: list[float] = []

    for ep in range(n_episodes):
        all_log_probs: list[torch.Tensor] = []
        all_returns: list[float] = []
        batch_ep_returns: list[float] = []
        last_episode_stats: list[dict] = []

        for _ in range(batch_size):
            log_probs, rewards, last_episode_stats = run_episode(env, policy)
            returns = compute_returns(rewards, gamma)
            all_log_probs.extend(log_probs)
            all_returns.extend(returns)
            batch_ep_returns.append(float(sum(rewards)))

        returns_t = torch.tensor(all_returns, dtype=torch.float32)
        batch_mean = returns_t.mean().item()
        batch_var = returns_t.var().item()
        running_mean = (1 - baseline_alpha) * running_mean + baseline_alpha * batch_mean
        running_var = (1 - baseline_alpha) * running_var + baseline_alpha * batch_var

        advantages = (returns_t - running_mean) / (running_var ** 0.5 + 1e-8)
        loss = -(torch.stack(all_log_probs) * advantages).sum()

        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(policy.parameters(), max_norm=1.0)
        optimizer.step()

        avg_ep_return = float(np.mean(batch_ep_returns))
        episode_returns.append(avg_ep_return)
        losses.append(loss.item())

        if (ep + 1) % log_every == 0:
            avg_return = np.mean(episode_returns[-log_every:])
            avg_loss = np.mean(losses[-log_every:])
            buffer_stats = "  ".join(
                f"{s['node_id']} Lq={s['Lq']:.3f} W={s['W']:.3f}"
                for s in last_episode_stats
                if s.get("node_kind") == "buffer"
            )
            print(
                f"ep {ep + 1:4d}/{n_episodes}"
                f"  avg_return={avg_return:8.2f}"
                f"  avg_loss={avg_loss:8.3f}"
                + (f"  [{buffer_stats}]" if buffer_stats else "")
            )

    return episode_returns, losses


def _smooth(data: list[float], window: int) -> np.ndarray:
    return np.convolve(data, np.ones(window) / window, mode="valid")


def plot(
    episode_returns: list[float],
    losses: list[float],
    smooth_window: int = 20,
    save_path: str = "training_curve_scheduling.png",
) -> None:
    n = len(episode_returns)
    episodes = np.arange(1, n + 1)

    fig, axes = plt.subplots(2, 1, figsize=(10, 7))
    fig.suptitle("REINFORCE — SharedStationSchedulingGym", fontsize=14)

    ax = axes[0]
    ax.plot(episodes, episode_returns, alpha=0.25, color="steelblue", linewidth=0.8)
    if n >= smooth_window:
        smoothed = _smooth(episode_returns, smooth_window)
        x_sm = np.arange(smooth_window, n + 1)
        ax.plot(x_sm, smoothed, color="steelblue", linewidth=2, label=f"{smooth_window}-ep moving avg")
    ax.set_ylabel("Cumulative Return")
    ax.set_xlabel("Episode")
    ax.set_title("Episode Return (higher = shorter buffer queues)")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.plot(episodes, losses, alpha=0.25, color="tomato", linewidth=0.8)
    if n >= smooth_window:
        smoothed = _smooth(losses, smooth_window)
        x_sm = np.arange(smooth_window, n + 1)
        ax.plot(x_sm, smoothed, color="tomato", linewidth=2, label=f"{smooth_window}-ep moving avg")
    ax.set_ylabel("Policy Gradient Loss")
    ax.set_xlabel("Episode")
    ax.set_title("REINFORCE Loss")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Saved {save_path}")
    plt.show()


if __name__ == "__main__":
    episode_returns, losses = train()
    plot(episode_returns, losses)
