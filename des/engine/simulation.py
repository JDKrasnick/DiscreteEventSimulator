from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from des.engine.scheduler import Scheduler

if TYPE_CHECKING:
    from des.nodes.base import Node


class Simulation:
    def __init__(self, warm_up_time: float = 0.0) -> None:
        self.clock: float = 0.0
        self.warm_up_time: float = warm_up_time
        self.scheduler: Scheduler = Scheduler()
        self._nodes: dict[str, Node] = {}

    def register(self, node: Node) -> None:
        self._nodes[node.node_id] = node

    def run(self, until: float, on_refresh: "Callable[[float, float], None] | None" = None, refresh_interval: float = 10.0) -> None:
        next_refresh = self.clock + refresh_interval
        while not self.scheduler.is_empty():
            next_time = self.scheduler.peek_time()
            if next_time is None or next_time > until:
                break
            event = self.scheduler.pop_next()
            self.clock = event.time
            node = self._nodes.get(event.target_id)
            if node is None:
                raise KeyError(f"No node registered with id '{event.target_id}'")
            node.handle(event)
            if on_refresh is not None and self.clock >= next_refresh:
                on_refresh(self.clock, until)
                next_refresh = self.clock + refresh_interval
        if on_refresh is not None:
            on_refresh(self.clock, until)

    @property
    def warmed_up(self) -> bool:
        return self.clock >= self.warm_up_time
