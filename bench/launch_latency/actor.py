from __future__ import annotations

import ray

from aeris.behavior import action
from aeris.behavior import Behavior


class AerisActor(Behavior):
    @action
    def noop(self) -> None:
        return None


class DaskActor:
    def noop(self) -> None:
        return None


@ray.remote
class RayActor:
    def exit(self) -> None:
        ray.actor.exit_actor()

    def noop(self) -> None:
        return None
