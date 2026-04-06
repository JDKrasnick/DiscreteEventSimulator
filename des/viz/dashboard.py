from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from rich.console import Console
from rich.table import Table

from des.viz.network_plot import draw_network
from des.viz.timeseries import plot_queue_lengths, plot_utilization

if TYPE_CHECKING:
    from des.network.network import QueueingNetwork


def show_dashboard(net: QueueingNetwork, title: str = "DES Dashboard", save_path: str | None = None) -> None:
    """
    Render a 2x2 dashboard:
      Top-left:  network topology
      Top-right: queue length time series
      Bottom-left: utilization bar chart
      Bottom-right: stats summary table (as text)
    """
    fig = plt.figure(figsize=(16, 10))
    fig.suptitle(title, fontsize=14, fontweight="bold")
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)

    ax_topo  = fig.add_subplot(gs[0, 0])
    ax_ts    = fig.add_subplot(gs[0, 1])
    ax_util  = fig.add_subplot(gs[1, 0])
    ax_stats = fig.add_subplot(gs[1, 1])

    draw_network(net, ax=ax_topo)
    plot_queue_lengths(net, ax=ax_ts)
    plot_utilization(net, ax=ax_util)
    _render_stats_table(net, ax=ax_stats)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Dashboard saved to {save_path}")
    else:
        plt.show()


def print_stats_table(net: QueueingNetwork) -> None:
    """Print a rich stats table to the terminal."""
    table = Table(title="Simulation Statistics")
    table.add_column("Node", style="cyan")
    table.add_column("Arrivals", justify="right")
    table.add_column("Departures", justify="right")
    table.add_column("W", justify="right")
    table.add_column("Wq", justify="right")
    table.add_column("L", justify="right")
    table.add_column("Lq", justify="right")

    for s in net.stats():
        table.add_row(
            s["node_id"],
            str(s["arrivals"]),
            str(s["departures"]),
            f"{s['W']:.4f}",
            f"{s['Wq']:.4f}",
            f"{s['L']:.4f}",
            f"{s['Lq']:.4f}",
        )
    Console().print(table)


def _render_stats_table(net: QueueingNetwork, ax: plt.Axes) -> None:
    """Render stats as a matplotlib table in the given axes."""
    ax.axis("off")
    stats = net.stats()
    if not stats:
        return

    col_labels = ["Node", "Arrivals", "W", "Wq", "L", "Lq"]
    rows = [
        [s["node_id"], str(s["arrivals"]), f"{s['W']:.3f}", f"{s['Wq']:.3f}", f"{s['L']:.3f}", f"{s['Lq']:.3f}"]
        for s in stats
    ]

    table = ax.table(
        cellText=rows,
        colLabels=col_labels,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.6)
    ax.set_title("Statistics Summary", fontsize=11)
