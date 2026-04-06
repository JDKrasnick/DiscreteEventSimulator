from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np

if TYPE_CHECKING:
    from des.network.network import QueueingNetwork


def plot_queue_lengths(net: QueueingNetwork, ax: plt.Axes | None = None, max_points: int = 5000) -> plt.Axes:
    """
    Plot queue length over time for each server using recorded snapshots.
    Downsamples to max_points for rendering efficiency.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(10, 4))

    for node_id, server in net._servers.items():
        snaps = server.snapshots
        if not snaps:
            continue
        times, q_lens, _ = zip(*snaps)
        times = np.array(times)
        q_lens = np.array(q_lens)

        if len(times) > max_points:
            idx = np.linspace(0, len(times) - 1, max_points, dtype=int)
            times = times[idx]
            q_lens = q_lens[idx]

        ax.step(times, q_lens, where="post", label=node_id, alpha=0.8)

    ax.set_xlabel("Time")
    ax.set_ylabel("Queue Length (Lq)")
    ax.set_title("Queue Length Over Time")
    ax.legend()
    ax.grid(True, alpha=0.3)
    return ax


def plot_utilization(net: QueueingNetwork, ax: plt.Axes | None = None) -> plt.Axes:
    """Bar chart of current server utilization."""
    if ax is None:
        _, ax = plt.subplots(figsize=(6, 4))

    node_ids = list(net._servers.keys())
    utils = [net._servers[nid].utilization for nid in node_ids]
    colors = [(min(1.0, u), 1.0 - min(1.0, u) * 0.8, 1.0 - min(1.0, u) * 0.8) for u in utils]

    bars = ax.bar(node_ids, utils, color=colors, edgecolor="black", linewidth=0.8)
    ax.axhline(1.0, color="red", linestyle="--", linewidth=1, label="100% utilization")
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Utilization ρ")
    ax.set_title("Server Utilization")
    ax.legend()

    for bar, u in zip(bars, utils):
        ax.text(bar.get_x() + bar.get_width() / 2, u + 0.02, f"{u:.2f}", ha="center", va="bottom", fontsize=9)

    return ax
