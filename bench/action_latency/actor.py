from __future__ import annotations

import os
import random
import statistics
from typing import Any
from typing import NamedTuple

import ray
from proxystore.utils.timer import Timer

from academy.agent import action
from academy.agent import Agent
from academy.handle import Handle


def randbytes(size: int) -> bytes:
    if size <= 100_000_000:  # noqa: PLR2004
        return random.randbytes(size)
    else:
        return os.urandom(size)


class Data(NamedTuple):
    msg_index: int
    raw: bytes

    @classmethod
    def new(cls, size: int) -> Data:
        return cls(msg_index=0, raw=randbytes(size))

    def len(self) -> int:
        return len(self.raw)


class AcademyRequestActor(Agent):
    def __init__(self, peer: Handle[AcademyReplyActor]) -> None:
        self.peer = peer

    @action
    async def noop(self) -> None:
        return None

    @action
    async def run(self, size: int, trials: int) -> tuple[float, float]:
        results = []

        data = Data.new(size)
        for _ in range(trials):
            with Timer() as timer:
                result = await self.peer.process(data)
                assert len(result) == len(data)
            results.append(timer.elapsed_s)
            data = Data(data.msg_index + 1, data.raw)

        mean = sum(results) / len(results)
        stdev = statistics.stdev(results)
        return mean, stdev


class AcademyReplyActor(Agent):
    @action
    async def noop(self) -> None:
        return None

    @action
    async def process(self, payload: Data) -> Data:
        return Data(payload.msg_index + 1, payload.raw)


class DaskRequestActor:
    def __init__(self, peer: Any) -> None:
        self.peer = peer

    def noop(self) -> None:
        return None

    def run(self, size: int, trials: int) -> tuple[float, float]:
        results = []

        data = Data.new(size)
        for _ in range(trials):
            with Timer() as timer:
                future = self.peer.process(data)
                result = future.result(timeout=60)
                assert len(result) == len(data)
            results.append(timer.elapsed_s)
            data = Data(data.msg_index + 1, data.raw)

        mean = sum(results) / len(results)
        stdev = statistics.stdev(results)
        return mean, stdev


class DaskReplyActor:
    def noop(self) -> None:
        return None

    def process(self, payload: Data) -> Data:
        return Data(payload.msg_index + 1, payload.raw)


@ray.remote
class RayRequestActor:
    def __init__(self, peer: Any) -> None:
        self.peer = peer

    def exit(self) -> None:
        ray.actor.exit_actor()

    def noop(self) -> None:
        return None

    def run(self, size: int, trials: int) -> tuple[float, float]:
        results = []

        data = Data.new(size)
        for _ in range(trials):
            with Timer() as timer:
                ref = self.peer.process.remote(data)
                result = ray.get(ref, timeout=60)
                assert len(result) == len(data)
            results.append(timer.elapsed_s)
            data = Data(data.msg_index + 1, data.raw)

        mean = sum(results) / len(results)
        stdev = statistics.stdev(results)
        return mean, stdev


@ray.remote
class RayReplyActor:
    def exit(self) -> None:
        ray.actor.exit_actor()

    def noop(self) -> None:
        return None

    def process(self, payload: Data) -> Data:
        return Data(payload.msg_index + 1, payload.raw)
