from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable, Literal, cast

if TYPE_CHECKING:
    from des.nodes.server import MMcServer


Discipline = Literal["FIFO", "FBFS", "LBFS"]
_UNSET_DISCIPLINE = object()


class ServerQueuePolicy(ABC):
    @abstractmethod
    def choose_job(self, server: MMcServer, jobs: list[dict]) -> int:
        """Return the index of the next waiting job to start service."""
        ...


class FifoServerQueuePolicy(ServerQueuePolicy):
    def choose_job(self, server: MMcServer, jobs: list[dict]) -> int:
        return 0


class FbfsServerQueuePolicy(ServerQueuePolicy):
    def choose_job(self, server: MMcServer, jobs: list[dict]) -> int:
        return min(range(len(jobs)), key=lambda idx: jobs[idx].get("stage", 0))


class LbfsServerQueuePolicy(ServerQueuePolicy):
    def choose_job(self, server: MMcServer, jobs: list[dict]) -> int:
        return max(range(len(jobs)), key=lambda idx: jobs[idx].get("stage", 0))


class CallbackServerQueuePolicy(ServerQueuePolicy):
    def __init__(self, fn: Callable[[MMcServer, list[dict]], int]) -> None:
        self.fn = fn

    def choose_job(self, server: MMcServer, jobs: list[dict]) -> int:
        return self.fn(server, jobs)


_DISCIPLINE_TO_POLICY: dict[Discipline, type[ServerQueuePolicy]] = {
    "FIFO": FifoServerQueuePolicy,
    "FBFS": FbfsServerQueuePolicy,
    "LBFS": LbfsServerQueuePolicy,
}


def queue_policy_from_discipline(discipline: Discipline) -> ServerQueuePolicy:
    try:
        return _DISCIPLINE_TO_POLICY[discipline]()
    except KeyError as exc:
        raise ValueError(f"Unknown discipline: {discipline}") from exc


def resolve_server_queue_policy(
    queue_policy: ServerQueuePolicy | None = None,
    discipline: Discipline | object = _UNSET_DISCIPLINE,
    *,
    warn_on_deprecated_discipline: bool = False,
    context: str = "discipline",
) -> ServerQueuePolicy:
    if queue_policy is not None:
        return queue_policy
    if discipline is _UNSET_DISCIPLINE or discipline is None:
        return FifoServerQueuePolicy()
    if warn_on_deprecated_discipline:
        warnings.warn(
            f"`{context}` is deprecated; use `queue_policy=` instead.",
            DeprecationWarning,
            stacklevel=3,
        )
    return queue_policy_from_discipline(cast(Discipline, discipline))
