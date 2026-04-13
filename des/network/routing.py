from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Callable


class RoutingPolicy(ABC):
    @abstractmethod
    def next_node(self, customer: dict, successors: list[tuple[str, float]]) -> str:
        """Return the id of the next node given a list of (node_id, weight) pairs."""
        ...


class ProbabilisticRouter(RoutingPolicy):
    """Routes customers by sampling from a discrete probability distribution."""

    def next_node(self, customer: dict, successors: list[tuple[str, float]]) -> str:
        if not successors:
            raise ValueError("No successor nodes to route to.")
        nodes, weights = zip(*successors)
        total = sum(weights)
        normalized = [w / total for w in weights]
        return random.choices(nodes, weights=normalized, k=1)[0]


class RoundRobinRouter(RoutingPolicy):
    """Routes customers to successors in round-robin order."""

    def __init__(self) -> None:
        self._index: int = 0

    def next_node(self, customer: dict, successors: list[tuple[str, float]]) -> str:
        if not successors:
            raise ValueError("No successor nodes to route to.")
        node_id = successors[self._index % len(successors)][0]
        self._index += 1
        return node_id


class ClassBasedRouter(RoutingPolicy):
    """Routes customers based on their 'class' field to a fixed destination.

    routes maps customer class name -> next node id.
    fallback is used when the customer's class is not in routes (optional).

    Example:
        ClassBasedRouter({"class1": "S2", "class3": "sink3"})
    """

    def __init__(self, routes: dict[str, str], fallback: str | None = None) -> None:
        self.routes = routes
        self.fallback = fallback

    def next_node(self, customer: dict, successors: list[tuple[str, float]]) -> str:
        cls = customer.get("class")
        if cls is None:
            raise ValueError(
                f"Customer {customer.get('id')} has no 'class' field. "
                "Set customer_class on the source or tag customers manually."
            )
        if cls not in self.routes:
            if self.fallback is not None:
                return self.fallback
            raise ValueError(
                f"No route defined for class '{cls}'. "
                f"Known classes: {list(self.routes.keys())}"
            )
        return self.routes[cls]


class CallbackRouter(RoutingPolicy):
    """Routes customers via an externally supplied callable.

    The callable receives the customer dict and the successor list and must
    return the id of the next node.  This is the integration point for RL
    agents: wrap the agent's action-selection logic in a function and pass it
    here.

    Example:
        def my_policy(customer, successors):
            return successors[agent.act(obs)][0]

        network.set_router(CallbackRouter(my_policy))
    """

    def __init__(self, fn: Callable[[dict, list[tuple[str, float]]], str]) -> None:
        self.fn = fn

    def next_node(self, customer: dict, successors: list[tuple[str, float]]) -> str:
        return self.fn(customer, successors)
