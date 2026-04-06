"""
M/M/c comparison: c=1, 2, 4 at rho=0.9 total load.

With lambda=0.9 and mu=1.0:
  c=1: rho_per_server=0.9  Lq~8.1
  c=2: rho_per_server=0.45 Lq~0.23
  c=4: rho_per_server=0.225 Lq~very small

Shows dramatic queue reduction from adding servers.
"""
import random

import matplotlib.pyplot as plt
from rich.console import Console
from rich.table import Table

from des.network.network import QueueingNetwork

LAM = 0.9
MU  = 1.0
END = 150_000

results = {}

for c in [1, 2, 4]:
    random.seed(42)
    net = QueueingNetwork(warm_up_time=500.0)
    net.add_source("source", arrival_rate=LAM, next_node_id="server")
    net.add_server("server", service_rate=MU, c=c)
    net.add_sink("sink")
    net.add_edge("source", "server")
    net.add_edge("server", "sink")
    net.run(until=END)
    results[c] = net.stats()[0]

table = Table(title=f"M/M/c Comparison  λ={LAM}  μ={MU}  ρ_total={LAM/MU}")
table.add_column("c", style="cyan", justify="center")
table.add_column("ρ/server", justify="right")
table.add_column("W (sim)", justify="right")
table.add_column("Wq (sim)", justify="right")
table.add_column("Arrivals", justify="right")

for c, s in results.items():
    table.add_row(
        str(c),
        f"{LAM / (c * MU):.3f}",
        f"{s['W']:.4f}",
        f"{s['Wq']:.4f}",
        str(s["arrivals"]),
    )

Console().print(table)

# Bar chart comparison
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
fig.suptitle(f"M/M/c Comparison  λ={LAM}  μ={MU}", fontsize=13)

cs = list(results.keys())
wq_vals = [results[c]["Wq"] for c in cs]
w_vals  = [results[c]["W"]  for c in cs]

axes[0].bar([str(c) for c in cs], wq_vals, color=["#e74c3c", "#e67e22", "#2ecc71"])
axes[0].set_xlabel("Number of servers (c)")
axes[0].set_ylabel("Mean wait time Wq")
axes[0].set_title("Mean Queue Wait (Wq)")
for i, v in enumerate(wq_vals):
    axes[0].text(i, v + 0.05, f"{v:.2f}", ha="center", fontsize=9)

axes[1].bar([str(c) for c in cs], w_vals, color=["#e74c3c", "#e67e22", "#2ecc71"])
axes[1].set_xlabel("Number of servers (c)")
axes[1].set_ylabel("Mean sojourn time W")
axes[1].set_title("Mean Sojourn Time (W)")
for i, v in enumerate(w_vals):
    axes[1].text(i, v + 0.05, f"{v:.2f}", ha="center", fontsize=9)

plt.tight_layout()
plt.show()
