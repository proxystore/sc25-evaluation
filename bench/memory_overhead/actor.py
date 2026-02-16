from __future__ import annotations

import ray

from academy.agent import action
from academy.agent import Agent


class AcademyActor(Agent):
    @action
    async def noop(self) -> None:
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
