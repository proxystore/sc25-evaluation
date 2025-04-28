from __future__ import annotations

import asyncio
import dataclasses
import logging

from autogen_core import AgentId
from autogen_core import message_handler
from autogen_core import MessageContext
from autogen_core import RoutedAgent
from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntime
from proxystore.utils.data import readable_to_bytes
from proxystore.utils.timer import Timer

from aeris.logging import init_logging


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


class Leader(RoutedAgent):
    def __init__(self, logger: logging.Logger) -> None:
        super().__init__('leader')
        self.logger = logger
        self.follower = AgentId('follower', 'default')

    @message_handler(strict=False)
    async def on_run(
        self,
        message: RunMessage,
        ctx: MessageContext,
    ) -> ResultMessage:
        content = 'x' * readable_to_bytes(message.size)
        # self.logger.info("Size of message: %d", sys.getsizeof(content))

        content_message = ContentMessage(0, content)
        with Timer() as timer:
            for _ in range(message.count):
                content_message = await self.send_message(
                    content_message,
                    self.follower,
                )

        return ResultMessage(timer.elapsed_s)
        # self.logger.info(
        #     "Completed run (size: %d, time: %.3d)",
        #     message.size,
        #     timer.elapsed_s,
        # )

    @message_handler
    async def on_result(
        self,
        message: ResultMessage,
        ctx: MessageContext,
    ) -> ResultMessage:
        raise AssertionError

    @message_handler
    async def on_content(
        self,
        message: ContentMessage,
        ctx: MessageContext,
    ) -> ContentMessage:
        # raise AssertionError
        return message


class Follower(RoutedAgent):
    def __init__(self, logger: logging.Logger) -> None:
        super().__init__('follower')
        self.logger = logger

    @message_handler
    async def on_run(
        self,
        message: RunMessage,
        ctx: MessageContext,
    ) -> ResultMessage:
        raise AssertionError

    @message_handler
    async def on_result(
        self,
        message: ResultMessage,
        ctx: MessageContext,
    ) -> ResultMessage:
        raise AssertionError

    @message_handler
    async def on_content(
        self,
        message: ContentMessage,
        ctx: MessageContext,
    ) -> ContentMessage:
        return ContentMessage(message.seq + 1, message.content)


async def main(logger: logging.Logger) -> None:
    repeat = 5
    message_count = 10
    sizes = ['1kb', '10kb', '100kb', '1mb', '4mb']

    # runtime = SingleThreadedAgentRuntime()
    # runtime.start()

    leader = GrpcWorkerAgentRuntime(host_address='localhost:50051')
    await leader.start()
    await Leader.register(leader, 'leader', lambda: Leader(logger))

    follower = GrpcWorkerAgentRuntime(host_address='localhost:50051')
    await follower.start()
    await Follower.register(follower, 'follower', lambda: Follower(logger))

    leader_id = AgentId('leader', 'default')
    for size in sizes:
        message = RunMessage(count=message_count, size=size)
        for i in range(repeat):
            result = await leader.send_message(message, leader_id)
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
    init_logging(level=logging.WARNING)
    logger = logging.getLogger('main')

    asyncio.run(main(logger))
