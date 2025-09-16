from __future__ import annotations

import asyncio
import time

import ray

from academy.agent import action
from academy.agent import Agent


class AcademyActor(Agent):
    @action
    async def noop(self, sleep: float = 0) -> None:
        await asyncio.sleep(sleep)


class DaskActor:
    def noop(self, sleep: float = 0) -> None:
        time.sleep(sleep)


@ray.remote
class RayActor:
    def exit(self) -> None:
        ray.actor.exit_actor()

    def noop(self, sleep: float = 0) -> None:
        time.sleep(sleep)
