from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from des.engine.event import Event
    from des.engine.simulation import Simulation


class Node(ABC):
    def __init__(self, node_id: str, simulation: Simulation) -> None:
        self.node_id = node_id
        self.sim = simulation
        simulation.register(self)

    @abstractmethod
    def handle(self, event: Event) -> None: ...
