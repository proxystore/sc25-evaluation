from __future__ import annotations

import random
import statistics
from typing import NamedTuple

import ray
from proxystore.utils.timer import Timer

from aeris.behavior import action
from aeris.behavior import Behavior
from aeris.handle import Handle


class Data(NamedTuple):
    raw: bytes

    def len(self) -> int:
        return len(self.raw)


class AerisRequestActor(Behavior):
    def __init__(self, peer: Handle[AerisReplyActor]) -> None:
        self.peer = peer

    @action
    def noop(self) -> None:
        return None

    @action
    def run(self, size: int, trials: int) -> tuple[str, str]:
        results = []

        for _ in range(trials):
            with Timer() as timer:
                payload = Data(random.randbytes(size))
                future = self.peer.action('process', payload)
                result = future.result(timeout=60)
                assert len(result) == len(payload)
            results.append(timer.elapsed_s)

        mean = sum(results) / len(results)
        stdev = statistics.stdev(results)
        return mean, stdev


class AerisReplyActor(Behavior):
    @action
    def noop(self) -> None:
        return None

    @action
    def process(self, payload: Data) -> None:
        return Data(random.randbytes(payload.len()))


class DaskRequestActor:
    def __init__(self, peer) -> None:
        self.peer = peer

    def noop(self) -> None:
        return None

    def run(self, size: int, trials: int) -> tuple[str, str]:
        results = []

        for _ in range(trials):
            with Timer() as timer:
                payload = Data(random.randbytes(size))
                future = self.peer.process(payload)
                result = future.result(timeout=60)
                assert len(result) == len(payload)
            results.append(timer.elapsed_s)

        mean = sum(results) / len(results)
        stdev = statistics.stdev(results)
        return mean, stdev


class DaskReplyActor(Behavior):
    def noop(self) -> None:
        return None

    def process(self, payload: Data) -> None:
        return Data(random.randbytes(payload.len()))


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

        for _ in range(trials):
            with Timer() as timer:
                payload = Data(random.randbytes(size))
                ref = self.peer.process.remote(payload)
                result = ray.get(ref, timeout=60)
                assert len(result) == len(payload)
            results.append(timer.elapsed_s)

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
        return Data(random.randbytes(payload.len()))
