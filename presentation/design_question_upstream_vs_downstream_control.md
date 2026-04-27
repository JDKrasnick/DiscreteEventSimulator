# Upstream vs Downstream Control

## Design Question

When we evaluate RL/ML policies in this simulator, where should the control decision live?

- Downstream control:
  after service finishes, decide where the job goes next
- Upstream control:
  when a resource becomes available, decide which waiting queue to serve next

This is the core design question behind routing-policy support versus scheduling-policy support.

## Current Repo Position

The repo currently supports both, but in different subsystems:

- Downstream control:
  legacy `server.router`
- Upstream control:
  explicit `station.scheduler`

That means the repository is already a hybrid simulator:

- routing-first for classic queue-network dispatching problems
- scheduling-first for shared-resource control problems

## What Downstream Control Means

Downstream control asks:

- Which successor should receive this completed job?
- Which branch should this job class take?
- How should outgoing flow be split after service?

In this repo, that is handled by legacy routed `server` nodes.

### Strengths

- Natural for routing and dispatching experiments
- Simple action semantics:
  choose one successor
- Easy to benchmark load balancing
- Works well for class-based branching and path selection
- Easy to expose in a standard event-driven RL loop

### Weaknesses

- Does not model shared-resource scheduling directly
- Hides queue ownership when the real decision is about waiting work
- Less faithful for re-entrant/shared-station systems

## What Upstream Control Means

Upstream control asks:

- Which buffer should this idle station pull from?
- Which waiting class should get service next?
- How should limited service capacity be allocated across multiple queues?

In this repo, that is handled by explicit `station` nodes and their schedulers.

### Strengths

- Matches real scheduling problems more closely
- Natural for shared stations and pull-based service
- Better fit for re-entrant queueing systems
- Better fit when queue competition is the central bottleneck

### Weaknesses

- Requires explicit queue ownership in the model
- Usually needs richer state than simple routing
- More complex when post-service branching is also class dependent

## Why This Matters for RL / ML

The choice changes the meaning of the action:

- Downstream RL action:
  choose where the completed job goes
- Upstream RL action:
  choose which queue gets service now

That affects:

- state representation
- action space design
- reward interpretation
- what “good control” even means

## QGym Comparison

QGym appears to center the control at the queue-service allocation layer rather than the downstream routing layer.

That makes it more naturally aligned with upstream control:

- allocate service to queues
- decide which queue/server pair receives work
- treat downstream queue transitions mostly as part of the environment dynamics

So relative to QGym:

- this repo has explicit downstream control that QGym does not emphasize
- this repo now also has an upstream scheduling subsystem for shared stations

## Practical Recommendation

Do not force a single abstraction to cover every queueing-control problem.

Use downstream control when the research question is:

- routing
- dispatching
- branching by class
- successor selection

Use upstream control when the research question is:

- scheduling
- priority
- shared-resource service order
- re-entrant/shared-station queueing behavior

## Recommended Framing for Presentation

### Key message

The simulator should support both control surfaces because they answer different queueing-control questions.

### One-line summary

- Downstream control decides where work goes next
- Upstream control decides what work gets served next

### Suggested conclusion

The repo’s additive design is a feature, not a compromise:

- legacy routed servers remain ideal for routing-policy benchmarks
- explicit buffers and stations enable scheduling-policy benchmarks
- together they allow broader RL/ML experimentation than either abstraction alone
