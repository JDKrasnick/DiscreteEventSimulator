from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class WelfordAccumulator:
    """Online mean and variance via Welford's algorithm."""
    n: int = 0
    mean: float = 0.0
    _M2: float = 0.0

    def update(self, value: float) -> None:
        self.n += 1
        delta = value - self.mean
        self.mean += delta / self.n
        self._M2 += delta * (value - self.mean)

    @property
    def variance(self) -> float:
        return self._M2 / (self.n - 1) if self.n > 1 else 0.0

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)


@dataclass
class TimeWeightedAccumulator:
    """Time-weighted mean: integral of f(t) dt / T."""
    _weighted_sum: float = 0.0
    _last_value: float = 0.0
    _last_time: float = 0.0
    _start_time: float = 0.0
    initialized: bool = False

    def start(self, time: float, initial_value: float = 0.0) -> None:
        self._last_time = time
        self._start_time = time
        self._last_value = initial_value
        self.initialized = True

    def update(self, time: float, new_value: float) -> None:
        if not self.initialized:
            return
        elapsed = time - self._last_time
        self._weighted_sum += self._last_value * elapsed
        self._last_value = new_value
        self._last_time = time

    def mean(self, current_time: float) -> float:
        if not self.initialized:
            return 0.0
        total_time = current_time - self._start_time
        if total_time <= 0:
            return 0.0
        elapsed = current_time - self._last_time
        total = self._weighted_sum + self._last_value * elapsed
        return total / total_time


@dataclass
class Collector:
    """Per-node statistics collector."""
    node_id: str
    sojourn: WelfordAccumulator = field(default_factory=WelfordAccumulator)
    wait: WelfordAccumulator = field(default_factory=WelfordAccumulator)
    queue_length: TimeWeightedAccumulator = field(default_factory=TimeWeightedAccumulator)
    system_length: TimeWeightedAccumulator = field(default_factory=TimeWeightedAccumulator)
    _arrivals: int = 0
    _departures: int = 0

    def record_arrival(self, time: float) -> None:
        self._arrivals += 1

    def record_departure(self, time: float, sojourn_time: float, wait_time: float) -> None:
        self._departures += 1
        self.sojourn.update(sojourn_time)
        self.wait.update(wait_time)

    def summary(self, current_time: float) -> dict:
        return {
            "node_id": self.node_id,
            "arrivals": self._arrivals,
            "departures": self._departures,
            "W": self.sojourn.mean,
            "Wq": self.wait.mean,
            "L": self.system_length.mean(current_time),
            "Lq": self.queue_length.mean(current_time),
        }
