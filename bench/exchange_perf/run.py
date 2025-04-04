from __future__ import annotations

import argparse
import logging
import os
import statistics
import sys
from collections.abc import Sequence
from datetime import datetime
from typing import NamedTuple

from proxystore.utils.data import readable_to_bytes
from proxystore.utils.timer import Timer

from aeris.exchange.proxystore import ProxyStoreExchange
from aeris.logging import init_logging
from aeris.manager import Manager
from bench.exchange_perf.agent import Data
from bench.exchange_perf.agent import ReplyAgent
from bench.argparse import add_aeris_parser_group
from bench.argparse import add_general_options
from bench.launcher import AerisConfig
from bench.results import CSVResultLogger

logger = logging.getLogger(__name__)


class Result(NamedTuple):
    exchange: str
    proxystore: bool
    data_size_bytes: int
    latency_s: float


def run_benchmark(
    manager: Manager,
    data_sizes: list[int],
    repeat: int,
    result_logger: CSVResultLogger,
) -> None:
    logger.info('Launching remote agent...')
    remote = manager.launch(ReplyAgent())
    remote.action('noop').result(timeout=30)
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
                future = remote.action('process', data)
                result = future.result(timeout=60)
                assert result.len() == data.len()

            result = Result(
                exchange=(
                    type(manager.exchange.exchange).__name__
                    if isinstance(manager.exchange, ProxyStoreExchange)
                    else type(manager.exchange).__name__
                ),
                proxystore=isinstance(manager.exchange, ProxyStoreExchange),
                data_size_bytes=data_size,
                latency_s=action_timer.elapsed_s,
            )
            result_logger.log(result)

        timer.stop()
        logger.info('Completed trials in %fs', timer.elapsed_s)

    logger.info('Shutting down remote agent...')
    remote.shutdown()
    manager.wait(remote.agent_id)
    logger.info('Remote agent shutdown!')


def run(
    *,
    config: AerisConfig,
    data_sizes: list[int],
    repeat: int,
    run_dir: str,
) -> None:
    timer = Timer().start()
    logger.info('Starting benchmark...')

    with config.get_launcher() as launcher:
        with CSVResultLogger(
            os.path.join(run_dir, 'results.csv'),
            Result,
        ) as result_logger:
            run_benchmark(launcher, data_sizes, repeat, result_logger)
        logger.info('Saved results to %s', result_logger.filepath)

    timer.stop()
    logger.info('Completed benchmark in %.3fs', timer.elapsed_s)


def main(argv: Sequence[str] | None = None) -> int:
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
    add_aeris_parser_group(parser, required=True)
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
    config = AerisConfig.from_args(vars(args), run_dir)

    run(
        config=config,
        data_sizes=[readable_to_bytes(x) for x in args.data_sizes],
        repeat=args.repeat,
        run_dir=run_dir,
    )

    return 0
