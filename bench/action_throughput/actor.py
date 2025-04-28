from __future__ import annotations

import time

import ray
from academy.behavior import action
from academy.behavior import Behavior


class AerisActor(Behavior):
    @action
    def noop(self, sleep: float = 0) -> None:
        time.sleep(sleep)


class DaskActor:
    def noop(self, sleep: float = 0) -> None:
        time.sleep(sleep)


@ray.remote
class RayActor:
    def exit(self) -> None:
        ray.actor.exit_actor()

    def noop(self, sleep: float = 0) -> None:
        time.sleep(sleep)
