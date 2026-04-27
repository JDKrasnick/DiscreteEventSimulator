# DiscreteEventSimulator

A web-based discrete event simulator for queueing networks with a drag-and-drop canvas UI and real-time streaming.

## Running

```bash
pip3 install -r requirements-api.txt
uvicorn api.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000).

## Features

### Network Builder
- Drag **Source**, **Server**, **Buffer**, **Station**, and **Sink** nodes onto the canvas
- Connect nodes by dragging between handles
- Click any node or edge to edit properties in the right panel

### Node Types
| Node | Purpose |
|------|---------|
| Source | Generates arrivals at rate λ (Poisson process) |
| Server | Processes customers at rate μ with c parallel servers |
| Buffer | Holds waiting work explicitly for a downstream shared station |
| Station | Shared service resource that pulls from one or more upstream buffers |
| Sink | Absorbs departing customers |

### Routing Policies (per server)
- **Probabilistic** — weighted random routing across outgoing edges
- **Round Robin** — cycles through downstream nodes evenly
- **Class-Based** — routes by customer class via a configurable class→target map

Server nodes display a badge (RR / CB) when a non-default routing policy is active.

### Queue Policies (per server)
- **FIFO** — serves the oldest waiting job first
- **FBFS** — serves the waiting job with the smallest `stage`
- **LBFS** — serves the waiting job with the largest `stage`

Server subtitles show the active queue policy inline as `Q=FIFO`, `Q=FBFS`, or `Q=LBFS`.

### Scheduling Policies (per station)
- **Round Robin** — cycles across upstream buffers, falling through if the chosen buffer is empty
- **First Non-Empty** — scans buffers in order and serves the first one with work
- **Longest Queue** — serves the buffer with the largest queue

### Uploaded Custom Policies
- Open **Policies** in the toolbar to upload Python policy files.
- Uploaded policies are separated in the UI by:
  - **Downstream / Server Routing**
  - **Local / Server Queue**
  - **Upstream / Station Scheduling**
- Server nodes can choose uploaded routing and queue policies.
- Station nodes can choose uploaded scheduling policies.

Upload files should define one or more of these module-level collections:

```python
from des.network.routing import RoutingPolicy
from des.network.scheduling import SchedulingPolicy
from des.network.server_queue import ServerQueuePolicy


class MyRouter(RoutingPolicy):
    def next_node(self, customer, successors):
        return successors[0][0]


class MyQueuePolicy(ServerQueuePolicy):
    def choose_job(self, server, jobs):
        return 0


class MyScheduler(SchedulingPolicy):
    def choose_buffer(self, station, buffers):
        return 0


ROUTERS = {"my_router": MyRouter}
SERVER_QUEUE_POLICIES = {"my_queue": MyQueuePolicy}
STATION_SCHEDULERS = {"my_scheduler": MyScheduler}
```

Each uploaded entry must be a zero-argument class or factory function that returns the matching policy type.

### Preset Templates
Click **Templates** to load a pre-built network:
- **M/M/1** — single server, λ=0.8, μ=1.0
- **M/M/c** — 3-server queue, λ=2.0, μ=1.0
- **Tandem** — two servers in series, λ=0.5
- **Shared Station** — explicit multi-buffer scheduling into one station
- **Rybko-Stolyar** — cross-coupled shared-station stress-test topology

### Simulation Controls
| Control | Description |
|---------|-------------|
| Until | Simulation end time |
| Warm-up | Time before stats collection begins |
| Stream Interval | How often live data is pushed (seconds) |
| ▶ Run | Stream a full simulation via WebSocket |
| ⏭ Step | Advance one event at a time |
| ■ Stop | Halt a running simulation |
| ↺ Reset | Clear state and chart |

### Metrics Panel (4 tabs)

**📊 Live** — live cards for explicit buffers, shared stations, and legacy servers.

**📈 Stats** — table of arrivals, departures, L, Lq, W, Wq per queue-owning node after each stream tick.

**✓ Theory** — compares legacy server nodes against M/M/1 / M/M/c closed-form results. Explicit buffer/station scheduling models show a “no analytic comparison” message here.

**📉 Chart** — rolling queue-length time series for explicit buffers and legacy servers.

## RL Examples

- `python3 train_rl.py` trains the existing routing-control policy.
- `python3 train_scheduling_rl.py` trains the new shared-station scheduling policy.

## API

The FastAPI backend is available at `/api`. Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs).

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/networks` | POST | Create a network session |
| `/api/networks/{id}` | DELETE | Delete a session |
| `/api/networks/{id}/stream` | WS | Stream simulation state |
| `/api/networks/{id}/step` | POST | Single-step the simulation |
| `/api/networks/{id}/stop` | POST | Stop a running simulation |
| `/api/policies` | GET | List uploaded custom policies grouped by usage |
| `/api/policies/upload` | POST | Upload a Python policy module |

## Notes

- Shared-station scheduling support is additive; legacy `source -> server -> sink` networks still work unchanged.
- Presentation-friendly rollout notes live in [SHARED_STATION_SCHEDULING_NOTES.md](./SHARED_STATION_SCHEDULING_NOTES.md).
