from __future__ import annotations

import asyncio
import dataclasses
import logging
from concurrent.futures import ProcessPoolExecutor

from proxystore.utils.data import readable_to_bytes
from proxystore.utils.timer import Timer

from academy.agent import action
from academy.agent import Agent
from academy.exchange import RedisExchangeFactory
from academy.handle import Handle
from academy.logging import init_logging
from academy.manager import Manager


@dataclasses.dataclass
class RunMessage:
    count: int
    size: str


@dataclasses.dataclass
class ContentMessage:
    seq: int
    content: str


@dataclasses.dataclass
class ResultMessage:
    runtime: float


class Leader(Agent):
    def __init__(self, follower: Handle[Follower]) -> None:
        self.follower = follower

    @action
    async def run(self, message: RunMessage) -> ResultMessage:
        content = 'x' * readable_to_bytes(message.size)

        content_message = ContentMessage(0, content)
        with Timer() as timer:
            for _ in range(message.count):
                content_message = await self.follower.action(
                    'reply',
                    content_message,
                )

        return ResultMessage(timer.elapsed_s)


class Follower(Agent):
    @action
    async def reply(self, message: ContentMessage) -> ContentMessage:
        return ContentMessage(message.seq + 1, message.content)


async def main(logger: logging.Logger) -> None:
    repeat = 5
    message_count = 10
    sizes = ['1kb', '10kb', '100kb', '1mb', '4mb']

    exchange = RedisExchangeFactory('localhost', 6380)
    executor = ProcessPoolExecutor(2)

    async with await Manager.from_exchange_factory(
        factory=exchange,
        executors=executor,
    ) as manager:
        follower = await manager.launch(Follower())
        leader = await manager.launch(Leader(follower))

        for size in sizes:
            message = RunMessage(count=message_count, size=size)
            for i in range(repeat):
                result: ResultMessage = await leader.action('run', message)
                logger.warning(
                    'Completed run %d/%d: size = %s; time = %.6f',
                    i + 1,
                    repeat,
                    message.size,
                    result.runtime,
                )


if __name__ == '__main__':
    logger = logging.getLogger('autogen_core')
    logger.setLevel(logging.WARNING)
    init_logging(level=logging.INFO)
    logger = logging.getLogger('main')

    raise SystemExit(asyncio.run(main(logger)))
