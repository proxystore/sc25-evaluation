from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from typing import NamedTuple

from proxystore.utils.data import readable_to_bytes
from proxystore.utils.timer import Timer

from academy.exchange import ProxyStoreExchangeFactory
from academy.logging import init_logging
from academy.manager import Manager
from bench.argparse import add_academy_parser_group
from bench.argparse import add_general_options
from bench.exchange_perf.agent import Data
from bench.exchange_perf.agent import ReplyAgent
from bench.launcher import AcademyConfig
from bench.results import CSVResultLogger

logger = logging.getLogger(__name__)


class Result(NamedTuple):
    exchange: str
    proxystore: bool
    data_size_bytes: int
    latency_s: float


def test_proxystore() -> tuple[str, ...]:
    from proxystore.endpoint.config import get_configs
    from proxystore.utils.environment import home_dir

    available_endpoints = get_configs(home_dir())
    return tuple(endpoint.uuid for endpoint in available_endpoints)


async def run_benchmark(
    manager: Manager[Any],
    data_sizes: list[int],
    repeat: int,
    result_logger: CSVResultLogger[Result],
) -> None:
    logger.info('Running warmup task...')
    assert manager._default_executor is not None
    executor = manager._executors[manager._default_executor]
    available_endpoints = executor.submit(test_proxystore).result()
    logger.info(f'Available endpoints: {available_endpoints}')

    logger.info('Launching remote agent...')
    remote = await manager.launch(
        ReplyAgent, 
        init_logging=True, 
        logfile="/flare/workflow_scaling/alokvk2/agents/sc25-evaluation/runs-test/{agent_id}-log.txt"
    )
    await remote.action('noop')
    logger.info('Remote agent is ready!')

    for data_size in data_sizes:
        logger.info(
            'Running with %d bytes for %d trials...',
            data_size,
            repeat,
        )
        timer = Timer().start()
        data = Data.new(data_size)

        for _ in range(repeat):
            with Timer() as action_timer:
                action_result: Data = await remote.action('process', data)
                assert action_result.len() == data.len()

            result = Result(
                exchange=(
                    type(manager.exchange_factory.base).__name__
                    if isinstance(
                        manager.exchange_factory,
                        ProxyStoreExchangeFactory,
                    )
                    else type(manager.exchange_factory).__name__
                ),
                proxystore=isinstance(
                    manager.exchange_factory,
                    ProxyStoreExchangeFactory,
                ),
                data_size_bytes=data_size,
                latency_s=action_timer.elapsed_s,
            )
            result_logger.log(result)

        timer.stop()
        logger.info('Completed trials in %fs', timer.elapsed_s)

    logger.info('Shutting down remote agent...')
    await remote.shutdown()
    await manager.wait((remote,))
    logger.info('Remote agent shutdown!')


async def run(
    *,
    config: AcademyConfig,
    data_sizes: list[int],
    repeat: int,
    run_dir: str,
) -> None:
    timer = Timer().start()
    logger.info('Starting benchmark...')

    async with config.get_launcher() as launcher:
        with CSVResultLogger(
            os.path.join(run_dir, 'results.csv'),
            Result,
        ) as result_logger:
            await run_benchmark(launcher, data_sizes, repeat, result_logger)
        logger.info('Saved results to %s', result_logger.filepath)

    timer.stop()
    logger.info('Completed benchmark in %.3fs', timer.elapsed_s)


async def main(argv: Sequence[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--data-sizes',
        type=str,
        nargs='+',
        help='data sizes to test',
    )
    add_general_options(parser)
    add_academy_parser_group(parser, required=True)
    args = parser.parse_args(argv)
    args.num_nodes = 1
    args.workers_per_node = 1

    run_dir = os.path.join(
        args.run_dir,
        'exchange-perf',
        datetime.now().strftime('%Y-%m-%d-%H-%M-%S'),
    )
    init_logging(
        level=args.log_level,
        logfile=os.path.join(run_dir, 'log.txt'),
        color=True,
        extra=False,
    )

    logger.info('Args: %s', vars(args))
    config = AcademyConfig.from_args(vars(args), run_dir)

    await run(
        config=config,
        data_sizes=[readable_to_bytes(x) for x in args.data_sizes],
        repeat=args.repeat,
        run_dir=run_dir,
    )

    return 0
