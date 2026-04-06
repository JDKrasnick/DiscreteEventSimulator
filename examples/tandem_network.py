"""
Tandem network: two M/M/1 servers in series.

  source -> server1 -> server2 -> sink

By Jackson's theorem, each server in a tandem network with Poisson
arrivals and independent exponential service times behaves as an
independent M/M/1 queue with the same arrival rate lambda.

Lambda=0.5, mu1=1.0, mu2=0.8
  server1: rho=0.5,  W_theory = 1/(1.0-0.5) = 2.0
  server2: rho=0.625, W_theory = 1/(0.8-0.5) = 3.33
"""
import random

from des.network.network import QueueingNetwork

random.seed(7)

LAM  = 0.5
MU1  = 1.0
MU2  = 0.8
END  = 200_000

net = QueueingNetwork(warm_up_time=1000.0)
net.add_source("source",  arrival_rate=LAM, next_node_id="server1")
net.add_server("server1", service_rate=MU1, c=1)
net.add_server("server2", service_rate=MU2, c=1)
net.add_sink("sink")

net.add_edge("source",  "server1")
net.add_edge("server1", "server2")
net.add_edge("server2", "sink")

net.run(until=END, cli=True, refresh_interval=500.0)
