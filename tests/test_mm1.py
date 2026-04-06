"""
M/M/1 analytic verification tests.

Closed-form steady-state formulas:
  rho = lam / mu
  L   = rho / (1 - rho)
  Lq  = rho^2 / (1 - rho)
  W   = 1 / (mu - lam)
  Wq  = rho / (mu - lam)
"""
import random

import pytest

from des.engine.simulation import Simulation
from des.nodes.server import MMcServer
from des.nodes.sink import Sink
from des.nodes.source import Source


def run_mm1(lam: float, mu: float, n_arrivals: int = 100_000, seed: int = 42) -> dict:
    random.seed(seed)
    # run until enough time has passed to generate n_arrivals at rate lam, with margin
    end_time = (n_arrivals / lam) * 1.5
    sim = Simulation(warm_up_time=end_time * 0.05)

    source = Source("source", sim, next_node_id="server", arrival_rate=lam)
    server = MMcServer("server", sim, service_rate=mu, c=1, next_node_id="sink")
    sink = Sink("sink", sim)

    source.start()
    sim.run(until=end_time)

    summary = server.collector.summary(sim.clock)
    return summary


@pytest.mark.parametrize("lam,mu,rho,tol", [
    (0.5, 1.0, 0.5, 0.05),
    (0.8, 1.0, 0.8, 0.05),
    (0.9, 1.0, 0.9, 0.10),  # high load: more variance, looser tolerance
])
def test_mm1_steady_state(lam, mu, rho, tol):
    n = 500_000 if rho >= 0.9 else 100_000
    summary = run_mm1(lam, mu, n_arrivals=n)

    W_theory  = 1 / (mu - lam)
    Wq_theory = rho / (mu - lam)

    assert abs(summary["W"]  - W_theory)  / W_theory  < tol, f"W  off: {summary['W']:.4f} vs {W_theory:.4f}"
    assert abs(summary["Wq"] - Wq_theory) / Wq_theory < tol, f"Wq off: {summary['Wq']:.4f} vs {Wq_theory:.4f}"
