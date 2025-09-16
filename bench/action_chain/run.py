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
from bench.action_chain.agent import Data
from bench.action_chain.agent import Node
from bench.argparse import add_academy_parser_group
from bench.argparse import add_general_options
from bench.launcher import AcademyConfig
from bench.results import CSVResultLogger

logger = logging.getLogger(__name__)


class Result(NamedTuple):
    exchange: str
    proxystore: bool
    chain_length: int
    data_size_bytes: int
    time_s: float


async def run_benchmark(
    manager: Manager[Any],
    chain_lengths: list[int],
    data_size_bytes: int,
    repeat: int,
    result_logger: CSVResultLogger[Result],
) -> None:
    for chain_length in chain_lengths:
        logger.info('Launching remote agents...')

        agent_ids = [
            await manager.register_agent(Node) for _ in range(chain_length)
        ]

        behaviors = []
        for i in range(len(agent_ids)):
            if i + 1 == len(agent_ids):
                behaviors.append(Node(None))
            else:
                handle = manager.get_handle(agent_ids[i + 1])
                behaviors.append(Node(handle))
        handles = [
            await manager.launch(behavior, registration=agent_id)
            for behavior, agent_id in zip(behaviors, agent_ids, strict=False)
        ]

        data = Data.new(data_size_bytes)
        logger.info('Running warm up...')
        await handles[0].process(data)

        logger.info(
            'Running with %d agents for %d trials...',
            chain_length,
            repeat,
        )
        timer = Timer().start()
        for _ in range(repeat):
            with Timer() as action_timer:
                result = await handles[0].process(data)
                assert result.len() == data.len()

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
                chain_length=chain_length,
                data_size_bytes=data_size_bytes,
                time_s=action_timer.elapsed_s,
            )
            result_logger.log(result)

        timer.stop()
        logger.info('Completed trials in %fs', timer.elapsed_s)

        logger.info('Shutting down remote agents...')
        for handle in handles:
            await handle.shutdown()
        await manager.wait(handles)
        logger.info('Remote agents shutdown!')


async def run(
    *,
    config: AcademyConfig,
    chain_lengths: list[int],
    data_size: int,
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
            await run_benchmark(
                launcher,
                chain_lengths,
                data_size,
                repeat,
                result_logger,
            )
        logger.info('Saved results to %s', result_logger.filepath)

    timer.stop()
    logger.info('Completed benchmark in %.3fs', timer.elapsed_s)


async def main(argv: Sequence[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--chain-lengths',
        type=int,
        nargs='+',
        help='chain lengths to test',
    )
    parser.add_argument(
        '--data-size',
        required=True,
        help='data size to test',
    )
    parser.add_argument('--workers-per-node', type=int, required=True)
    add_general_options(parser)
    add_academy_parser_group(parser, required=True)
    args = parser.parse_args(argv)
    args.num_nodes = 1

    run_dir = os.path.join(
        args.run_dir,
        'action-chain',
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
        chain_lengths=args.chain_lengths,
        data_size=readable_to_bytes(args.data_size),
        repeat=args.repeat,
        run_dir=run_dir,
    )

    return 0
