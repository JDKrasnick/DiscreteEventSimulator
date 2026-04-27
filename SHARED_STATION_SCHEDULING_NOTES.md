# Shared-Station Scheduling Notes

## Problem Statement

The simulator can already evaluate routing decisions, but it cannot represent the more common factory or service-center case where multiple waiting lines feed the same physical resource. That limits both the runtime model and the RL story: we can choose *where jobs go*, but not *which waiting job a shared station should serve next*.

## Why Routing-Only RL Is Insufficient

- Routing control assumes the decision happens when a job leaves a server.
- Shared-resource scheduling needs a decision when a station becomes idle.
- In a shared-station system, the key state is spread across multiple explicit buffers.
- A routing-only abstraction hides the queue ownership that a scheduling policy needs.

## Legacy Model vs Explicit Model

| Topic | Legacy Server Model | Explicit Buffer + Station Model |
|---|---|---|
| Waiting work | Inside `MMcServer` | Inside `Buffer` nodes |
| Service resource | `MMcServer` | `Station` node |
| Decision point | Server departure / routing | Station idle / scheduling |
| RL action | Choose downstream successor | Choose upstream buffer to serve |
| Backward compatibility | Preserved | Added alongside legacy |

## Before / After Topology

```text
Before
  source -> dispatcher(server) -> S1 or S2 -> sink

After
  src1 -> B1 \
              -> SharedStation -> sink
  src2 -> B2 /
```

## Event Lifecycle for Shared-Station Scheduling

1. A source sends work into a named `Buffer`.
2. Buffer arrival records queue state and notifies downstream stations.
3. If a station has idle capacity and any upstream buffer is non-empty, it schedules a `SCHEDULING_DECISION` event.
4. The station’s scheduler picks a preferred upstream buffer.
5. If that buffer is empty, the station falls through to the next non-empty buffer in deterministic order.
6. The station starts service immediately and schedules a departure event.
7. On departure, the completed job moves to the station’s single downstream successor and the station requests another decision if work remains.

## RL Decision Loop

- Observation:
  - all explicit buffer queue lengths in config order
  - then all explicit station busy-server counts in config order
- Action:
  - discrete choice among the controlled station’s upstream buffers
- Reward:
  - negative integrated total explicit-buffer queue length
- Termination:
  - normal episode end when the event queue empties
- Truncation:
  - max decision steps reached

## API and UI Changes

- API schema adds `buffer` and `station` node types.
- Station nodes add a `scheduler` field with `round_robin`, `first_non_empty`, or `longest_queue`.
- Live state remains additive:
  - `servers`
  - `buffers`
  - `stations`
- UI adds draggable Buffer and Station nodes, station scheduler editing, and a shared-station template.
- Theory view stays focused on legacy M/M/1 and M/M/c comparisons.

## Demo Topology for the First Rollout

- `src1 -> B1`
- `src2 -> B2`
- `B1, B2 -> SharedStation`
- `SharedStation -> sink`

This is small enough to explain on one slide and concrete enough to demonstrate both heuristic scheduling and the new RL environment.

## Backward Compatibility

- No legacy server behavior is removed.
- Existing routing APIs remain intact.
- Existing routing RL environment stays untouched.
- `QueueingNetwork.observe()` still returns legacy server state only.
- New shared-station state is exposed through additive system observation and API payloads.

## V1 Scope Decisions

- Additive design only; do not replace `MMcServer`.
- One RL-controlled station per environment.
- Explicit buffers are unbounded in v1.
- Stations schedule only among their incoming buffers.
- Stations have exactly one outgoing edge in v1.
- UI and API ship in the same rollout as engine support.

## Risks and Next Steps

- Finite-capacity buffers and backpressure are intentionally deferred.
- Multi-station coordinated control is out of scope for v1.
- Analytical queueing formulas do not directly cover the explicit scheduling model in the existing theory tab.
- Future follow-ups:
  - finite capacities and blocking semantics
  - multiple RL-controlled stations
  - richer service-time and arrival distributions
  - scheduling diagnostics and policy replay views
