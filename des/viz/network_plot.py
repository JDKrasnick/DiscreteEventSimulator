from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

if TYPE_CHECKING:
    from des.network.network import QueueingNetwork


def draw_network(net: QueueingNetwork, ax: plt.Axes | None = None, title: str = "Queueing Network") -> plt.Axes:
    """
    Draw the network topology. Node color encodes kind:
      - source: steel blue
      - server: color mapped to utilization (white -> red)
      - sink: gray
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 5))

    G = net.graph
    pos = nx.spring_layout(G, seed=42)

    node_colors = []
    node_labels = {}
    for node_id, data in G.nodes(data=True):
        kind = data.get("kind", "unknown")
        if kind == "source":
            node_colors.append("#4a90d9")
            lam = data.get("arrival_rate", "")
            node_labels[node_id] = f"{node_id}\nλ={lam}"
        elif kind == "server":
            server = net._servers.get(node_id)
            util = server.utilization if server else 0.0
            r = min(1.0, util)
            node_colors.append((1.0, 1.0 - r * 0.8, 1.0 - r * 0.8))
            mu = data.get("service_rate", "")
            c = data.get("c", 1)
            node_labels[node_id] = f"{node_id}\nμ={mu} c={c}"
        else:
            node_colors.append("#aaaaaa")
            node_labels[node_id] = node_id

    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors, node_size=1800, alpha=0.9)
    nx.draw_networkx_labels(G, pos, labels=node_labels, ax=ax, font_size=8)

    edge_labels = {
        (u, v): f"{d['weight']:.2f}" if d.get("weight", 1.0) != 1.0 else ""
        for u, v, d in G.edges(data=True)
    }
    nx.draw_networkx_edges(G, pos, ax=ax, arrows=True, arrowsize=20, edge_color="#555555", width=1.5)
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, ax=ax, font_size=7)

    ax.set_title(title, fontsize=12)
    ax.axis("off")
    return ax
