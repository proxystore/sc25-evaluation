from __future__ import annotations

import dataclasses
import logging
from concurrent.futures import ProcessPoolExecutor

from academy.behavior import action
from academy.behavior import Behavior
from academy.exchange.redis import RedisExchange
from academy.handle import Handle
from academy.launcher.executor import ExecutorLauncher
from academy.logging import init_logging
from academy.manager import Manager
from proxystore.utils.data import readable_to_bytes
from proxystore.utils.timer import Timer


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


class Leader(Behavior):
    def __init__(self, follower: Handle[Follower]) -> None:
        self.follower = follower

    @action
    def run(self, message: RunMessage) -> ResultMessage:
        content = 'x' * readable_to_bytes(message.size)

        content_message = ContentMessage(0, content)
        with Timer() as timer:
            for _ in range(message.count):
                content_message = self.follower.action(
                    'reply',
                    content_message,
                ).result()

        return ResultMessage(timer.elapsed_s)


class Follower(Behavior):
    @action
    def reply(self, message: ContentMessage) -> ContentMessage:
        return ContentMessage(message.seq + 1, message.content)


def main(logger: logging.Logger) -> None:
    repeat = 5
    message_count = 10
    sizes = ['1kb', '10kb', '100kb', '1mb', '4mb']

    exchange = RedisExchange('localhost', 6380)
    executor = ProcessPoolExecutor(2)

    with Manager(
        exchange=exchange,
        launcher=ExecutorLauncher(executor),
    ) as manager:
        follower = manager.launch(Follower())
        leader = manager.launch(Leader(follower))

        for size in sizes:
            message = RunMessage(count=message_count, size=size)
            for i in range(repeat):
                result = leader.action('run', message).result()
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

    main(logger)
