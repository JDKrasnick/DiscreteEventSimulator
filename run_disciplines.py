#!/usr/bin/env python3
"""Run M/M/1 with FIFO, FBFS, LBFS disciplines and print stats as JSON."""
import json
import random
import sys

sys.path.insert(0, "/Users/fastcheetah/Desktop/DiscreteEventSimulator")

from des.engine.event import EventType
from des.network.network import QueueingNetwork
from des.nodes.source import Source

ARRIVAL_RATE = 0.8
SERVICE_RATE = 1.0
WARM_UP = 2_000
RUN_UNTIL = 12_000
SEED = 42


class StagedSource(Source):
    def handle(self, event: object) -> None:
        self._customer_count += 1
        customer = {
            "id": self._customer_count,
            "arrival_time": self.sim.clock,
            "stage": random.randint(0, 3),
        }
        if self.customer_class is not None:
            customer["class"] = self.customer_class
        self.sim.scheduler.schedule(
            time=self.sim.clock,
            event_type=EventType.ARRIVAL,
            target_id=self.next_node_id,
            payload=customer,
        )
        delay = self._inter_arrival_fn()
        self.sim.scheduler.schedule(
            time=self.sim.clock + delay,
            event_type=EventType.ARRIVAL,
            target_id=self.node_id,
        )


def build_and_run(discipline: str) -> dict:
    random.seed(SEED)
    net = QueueingNetwork(warm_up_time=WARM_UP)

    net.add_source("src", arrival_rate=ARRIVAL_RATE, next_node_id="server")
    staged = StagedSource("src", net.sim, next_node_id="server", arrival_rate=ARRIVAL_RATE)
    net._sources[-1] = staged

    net.add_server("server", service_rate=SERVICE_RATE, c=1, discipline=discipline)
    net.add_sink("sink")
    net.add_edge("src", "server")
    net.add_edge("server", "sink")

    net.run(until=RUN_UNTIL)

    return next(s for s in net.stats() if s["node_id"] == "server")


results = {}
for disc in ("FIFO", "FBFS", "LBFS"):
    sys.stderr.write(f"Running {disc}...\n")
    results[disc] = build_and_run(disc)

print(json.dumps(results, indent=2))
