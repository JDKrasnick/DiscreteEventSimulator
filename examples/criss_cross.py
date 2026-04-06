"""
Criss-cross network (Figure 1.2).

  class1_src ──▶ S1 ──▶ S2 ──▶ sink_class2
  class3_src ──▶ S1 ──▶ sink_class3

Class 1 enters S1 then S2 then departs.
Class 3 enters S1 only then departs.
S1 is shared by both classes.
"""
import random

from des.network.network import QueueingNetwork
from des.network.routing import ClassBasedRouter

random.seed(42)

LAM1 = 0.3
LAM3 = 0.2
MU1  = 1.0   # S1 service rate
MU2  = 0.8   # S2 service rate

net = QueueingNetwork(warm_up_time=500.0)

net.add_source("class1_src", arrival_rate=LAM1, next_node_id="S1", customer_class="class1")
net.add_source("class3_src", arrival_rate=LAM3, next_node_id="S1", customer_class="class3")

net.add_server("S1", service_rate=MU1, c=1)
net.add_server("S2", service_rate=MU2, c=1)

net.add_sink("sink_class2")
net.add_sink("sink_class3")

# S1 routes class1 → S2, class3 → sink_class3
net.set_router(ClassBasedRouter({
    "class1": "S2",
    "class3": "sink_class3",
}))

net.add_edge("class1_src", "S1")
net.add_edge("class3_src", "S1")
net.add_edge("S1", "S2")
net.add_edge("S1", "sink_class3")
net.add_edge("S2", "sink_class2")

net.run(until=50_000, cli=True, refresh_interval=500.0)
