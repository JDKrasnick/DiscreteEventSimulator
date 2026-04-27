# Current Repo Support

## Overview

This repository currently supports two related but distinct queueing-control modes:

1. Legacy routing control with `source -> server -> sink` style networks
2. Explicit shared-station scheduling with `source -> buffer -> station -> ...` style networks

The design is additive. The newer buffer/station model does not replace the legacy server/router model.

## Engine and Runtime

### Legacy node model

- `Source`
  - Generates arrivals using Poisson/exponential inter-arrivals by default
  - Can tag jobs with a `customer_class`
- `MMcServer`
  - Supports exponential service with `c` parallel servers
  - Supports queue disciplines:
    - `FIFO`
    - `FBFS`
    - `LBFS`
- `Sink`
  - Absorbs completed jobs

### Legacy routing control

- Global routing policies:
  - `ProbabilisticRouter`
  - `RoundRobinRouter`
  - `ClassBasedRouter`
  - `CallbackRouter`
- Per-server router overrides are supported
- Class-based routing can use:
  - explicit class-to-target maps
  - optional fallback targets
- Routing decisions happen after service completes, on downstream movement

### Explicit scheduling model

- `Buffer`
  - Passive queue-owning node
  - Holds jobs explicitly
  - Tracks queue statistics
- `Station`
  - Shared service resource
  - Pulls jobs from upstream buffers
  - Has `service_rate` and `c`
  - Schedules one service start at a time through `SCHEDULING_DECISION` events
- Station scheduling policies:
  - `RoundRobinSchedulingPolicy`
  - `FirstNonEmptySchedulingPolicy`
  - `LongestQueueSchedulingPolicy`
  - `CallbackSchedulingPolicy`
- Scheduling decisions happen before service, on upstream selection

### Current explicit station constraints

- A `buffer` may only connect downstream to `station`
- A `station` may only receive work from `buffer`
- A `station` must have at least one incoming buffer
- A `station` must have exactly one outgoing edge
- A station successor may currently be:
  - `buffer`
  - `sink`
  - legacy `server`

### Current gap

- Explicit `station` nodes do not yet support class-based post-service branching
- Multi-branch downstream class routing is currently handled only by legacy `server` routers

## Configuration and API

### Supported API node types

- `source`
- `server`
- `sink`
- `buffer`
- `station`

### Supported server router config

- `probabilistic`
- `round_robin`
- `class_based`

Class-based server routing supports:
- `class_map`
- `fallback`

### Supported station scheduler config

- `round_robin`
- `first_non_empty`
- `longest_queue`

### API state and stats

- Live state includes:
  - `servers`
  - `buffers`
  - `stations`
- Stats currently include:
  - legacy server stats
  - buffer stats
- Station utilization/completion is exposed in live state, not the legacy `W/Wq/L/Lq` table

## RL / Gym Support

### Routing RL environment

- File: `des_gym.py`
- Environment: `DiscreteEventGym`
- Control type:
  - downstream routing choice
- Typical use:
  - dispatcher/server chooses which successor receives the completed job

### Scheduling RL environment

- File: `shared_station_gym.py`
- Environment: `SharedStationSchedulingGym`
- Control type:
  - upstream buffer selection for one controlled station
- Observation:
  - buffer queue lengths
  - station busy-server counts
- Reward:
  - negative integrated total explicit-buffer queue length

### Example training scripts

- `train_rl.py`
  - routing-control example
- `train_scheduling_rl.py`
  - shared-station scheduling example

## Frontend / UI

### Supported canvas node types

- Source
- Server
- Buffer
- Station
- Sink

### Supported UI editing

- Server router editing
  - including class map and fallback target
- Station scheduler editing
- Edge weight editing
- Source arrival/class editing

### Built-in templates

- M/M/1
- M/M/c
- Tandem
- Criss-Cross
- Shared Station
- Rybko-Stolyar

## What the Repo Supports Well Today

- Routing-policy experiments
- Load-balancing / dispatching experiments
- Shared-station scheduling experiments
- One controlled shared station for RL
- Mixed topologies that combine:
  - explicit buffers/stations
  - legacy server routers

## What the Repo Does Not Yet Support Natively

- Explicit station nodes with multiple outgoing class-based branches
- Multi-station RL control in one scheduling env
- Finite-capacity buffers / blocking semantics
- Native canonical re-entrant class transitions entirely inside the buffer/station subsystem
