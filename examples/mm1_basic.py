"""
Basic M/M/1 queue example.

Arrival rate lambda = 0.8, service rate mu = 1.0 => rho = 0.8
Theoretical:  L=4.0, Lq=3.2, W=5.0, Wq=4.0
"""
import random

from rich.console import Console
from rich.table import Table

from des.network.network import QueueingNetwork

random.seed(0)

LAM = 0.8
MU  = 1.0
RHO = LAM / MU

net = QueueingNetwork(warm_up_time=500.0)
net.add_source("source", arrival_rate=LAM, next_node_id="server")
net.add_server("server", service_rate=MU, c=1)
net.add_sink("sink")
net.add_edge("source", "server")
net.add_edge("server", "sink")

net.run(until=200_000, cli=True, refresh_interval=1000.0)

stats = net.stats()[0]

table = Table(title=f"M/M/1  λ={LAM}  μ={MU}  ρ={RHO}")
table.add_column("Metric", style="cyan")
table.add_column("Simulated", justify="right")
table.add_column("Theory", justify="right", style="green")

rows = [
    ("W  (mean sojourn)",   stats["W"],  1 / (MU - LAM)),
    ("Wq (mean wait)",      stats["Wq"], RHO / (MU - LAM)),
]

for name, sim_val, theory_val in rows:
    table.add_row(name, f"{sim_val:.4f}", f"{theory_val:.4f}")

Console().print(table)
