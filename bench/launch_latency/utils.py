from __future__ import annotations

from typing import NamedTuple


class Result(NamedTuple):
    framework: str
    num_nodes: int
    num_workers_per_node: int
    num_actors: int
    startup_time: float
    shutdown_time: float


class Times(NamedTuple):
    startup: float
    shutdown: float
