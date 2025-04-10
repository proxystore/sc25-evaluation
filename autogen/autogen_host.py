from __future__ import annotations

import asyncio
import logging

from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntimeHost

from aeris.logging import init_logging

logger = logging.getLogger('main')


async def main() -> None:
    host = GrpcWorkerAgentRuntimeHost(address='localhost:50051')
    host.start()

    try:
        await host.stop_when_signal()
    except KeyboardInterrupt:
        logger.info('Stopping...')
    finally:
        await host.stop()


if __name__ == '__main__':
    init_logging(logging.WARNING)
    asyncio.run(main())
