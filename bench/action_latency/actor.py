from __future__ import annotations

import os
import random
import statistics
from typing import NamedTuple

import ray
from academy.behavior import action
from academy.behavior import Behavior
from academy.handle import Handle
from proxystore.utils.timer import Timer


def randbytes(size: int) -> bytes:
    if size <= 100_000_000:  # noqa: PLR2004
        return random.randbytes(size)
    else:
        return os.urandom(size)


class Data(NamedTuple):
    index: int
    raw: list[bytes]

    @classmethod
    def new(cls, size: int) -> Data:
        # raw: list[bytes] = []
        # chunk_size = 10_000
        # for _ in range(size // chunk_size):
        #     raw.append(randbytes(chunk_size))
        # raw.append(randbytes(size % chunk_size))
        return cls(index=0, raw=randbytes(size))

    def len(self) -> int:
        return sum(len(r) for r in self.raw)


class AerisRequestActor(Behavior):
    def __init__(self, peer: Handle[AerisReplyActor]) -> None:
        self.peer = peer

    @action
    def noop(self) -> None:
        return None

    @action
    def run(self, size: int, trials: int) -> tuple[str, str]:
        results = []

        data = Data.new(size)
        for _ in range(trials):
            with Timer() as timer:
                future = self.peer.action('process', data)
                result = future.result(timeout=60)
                assert len(result) == len(data)
            results.append(timer.elapsed_s)
            data = Data(data.index + 1, data.raw)

        mean = sum(results) / len(results)
        stdev = statistics.stdev(results)
        return mean, stdev


class AerisReplyActor(Behavior):
    @action
    def noop(self) -> None:
        return None

    @action
    def process(self, payload: Data) -> None:
        return Data(payload.index + 1, payload.raw)


class DaskRequestActor:
    def __init__(self, peer) -> None:
        self.peer = peer

    def noop(self) -> None:
        return None

    def run(self, size: int, trials: int) -> tuple[str, str]:
        results = []

        data = Data.new(size)
        for _ in range(trials):
            with Timer() as timer:
                future = self.peer.process(data)
                result = future.result(timeout=60)
                assert len(result) == len(data)
            results.append(timer.elapsed_s)
            data = Data(data.index + 1, data.raw)

        mean = sum(results) / len(results)
        stdev = statistics.stdev(results)
        return mean, stdev


class DaskReplyActor(Behavior):
    def noop(self) -> None:
        return None

    def process(self, payload: Data) -> None:
        return Data(payload.index + 1, payload.raw)


@ray.remote
class RayRequestActor:
    def __init__(self, peer) -> None:
        self.peer = peer

    def exit(self) -> None:
        ray.actor.exit_actor()

    def noop(self) -> None:
        return None

    def run(self, size: int, trials: int) -> tuple[str, str]:
        results = []

        data = Data.new(size)
        for _ in range(trials):
            with Timer() as timer:
                ref = self.peer.process.remote(data)
                result = ray.get(ref, timeout=60)
                assert len(result) == len(data)
            results.append(timer.elapsed_s)
            data = Data(data.index + 1, data.raw)

        mean = sum(results) / len(results)
        stdev = statistics.stdev(results)
        return mean, stdev


@ray.remote
class RayReplyActor:
    def exit(self) -> None:
        ray.actor.exit_actor()

    def noop(self) -> None:
        return None

    def process(self, payload: Data) -> None:
        return Data(payload.index + 1, payload.raw)
