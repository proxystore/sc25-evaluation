from __future__ import annotations

import argparse
import asyncio
import logging
import os
import statistics
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from typing import NamedTuple

from globus_compute_sdk import Executor
from proxystore.utils.data import readable_to_bytes
from proxystore.utils.timer import Timer

from academy.logging import init_logging
from academy.manager import Manager
from bench.argparse import add_general_options
from bench.argparse import add_launcher_groups
from bench.launcher import get_launcher_config_from_args
from bench.launcher import is_academy_launcher
from bench.launcher import is_gc_launcher
from bench.launcher import LauncherConfig
from bench.remote_invocation.agent import AcademyStateActor
from bench.remote_invocation.agent import globus_compute_clean_state
from bench.remote_invocation.agent import globus_compute_init_state
from bench.remote_invocation.agent import globus_compute_read
from bench.results import CSVResultLogger

logger = logging.getLogger(__name__)


class Result(NamedTuple):
    framework: str
    trials: int
    state_size_bytes: int
    mean_latency_s: float
    stdev_latency_s: float


async def run_benchmark_academy(
    manager: Manager[Any],
    state_sizes: list[int],
    repeat: int,
    result_logger: CSVResultLogger[Result],
) -> None:
    logger.info('Running warmup task...')
    assert manager._default_executor is not None
    executor = manager._executors[manager._default_executor]
    executor.submit(sum, [1, 2, 3]).result()

    for state_size in state_sizes:
        logger.info('Starting actors...')
        state_handle = await manager.launch(
            AcademyStateActor,
            args=(state_size,),
        )
        await state_handle.action('noop')
        logger.info('Started actors')

        logger.info(
            'Running with %d bytes for %d trials...',
            state_size,
            repeat,
        )

        results = []
        for _ in range(repeat):
            with Timer() as timer:
                await state_handle.action('read')
            results.append(timer.elapsed_s)
        mean = sum(results) / len(results)
        std = statistics.stdev(results)
        result = Result(
            framework='Academy',
            trials=repeat,
            state_size_bytes=state_size,
            mean_latency_s=mean,
            stdev_latency_s=std,
        )
        result_logger.log(result)
        logger.info('Completed in %fs: %s', timer.elapsed_s, result)

        logger.info('Shutting down all actors...')
        await state_handle.shutdown()
        await manager.wait((state_handle,))
        logger.info('Shutdown all actors')

        logger.info('Waiting to avoid globus compute rate limits.')
        await asyncio.sleep(5)  # Avoid globus compute rate limits


def run_benchmark_globus_compute(
    executor: Executor,
    state_path: str,
    state_sizes: list[int],
    repeat: int,
    result_logger: CSVResultLogger[Result],
) -> None:
    logger.info('Running warmup task...')
    executor.submit(sum, [1, 2, 3]).result()

    for state_size in state_sizes:
        logger.info('Initializing state...')
        future = executor.submit(
            globus_compute_init_state,
            state_size,
            state_path,
        )
        future.result()
        logger.info('Initialized state.')

        logger.info(
            'Running with %d bytes for %d trials...',
            state_size,
            repeat,
        )

        results = []
        for _ in range(repeat):
            with Timer() as timer:
                future = executor.submit(globus_compute_read, state_path)
                future.result()
            results.append(timer.elapsed_s)
            time.sleep(5)  # Avoid Globus Compute rate limits
        mean = sum(results) / len(results)
        std = statistics.stdev(results)
        result = Result(
            framework='Globus Compute',
            trials=repeat,
            state_size_bytes=state_size,
            mean_latency_s=mean,
            stdev_latency_s=std,
        )
        result_logger.log(result)
        logger.info('Completed in %fs: %s', timer.elapsed_s, result)

        logger.info('Clenaing up state...')
        future = executor.submit(globus_compute_clean_state, state_path)
        future.result()
        logger.info('Shutdown all actors')
        time.sleep(5)  # Avoid Globus Compute rate limits


async def run_benchmark(
    launcher: Any,
    state_path: str | None,
    data_sizes: list[int],
    repeat: int,
    result_logger: CSVResultLogger[Result],
) -> None:
    if is_academy_launcher(launcher):
        return await run_benchmark_academy(
            launcher,
            data_sizes,
            repeat,
            result_logger,
        )
    elif is_gc_launcher(launcher):
        if state_path is None:
            raise ValueError('Must provide a path for globus compute state.')
        return run_benchmark_globus_compute(
            launcher,
            state_path,
            data_sizes,
            repeat,
            result_logger,
        )
    else:
        raise TypeError(f'Unsupported launcher type: {type(launcher)}.')


async def run(
    *,
    launcher_config: LauncherConfig[Any],
    state_path: str | None,
    state_sizes: list[int],
    repeat: int,
    run_dir: str,
) -> None:
    timer = Timer().start()
    logger.info('Starting benchmark...')

    async with launcher_config.get_launcher() as launcher:
        with CSVResultLogger(
            os.path.join(run_dir, 'results.csv'),
            Result,
        ) as result_logger:
            await run_benchmark(
                launcher,
                state_path,
                state_sizes,
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
        '--state-sizes',
        type=str,
        nargs='+',
        help='data sizes to test',
    )
    parser.add_argument(
        '--state-path',
        type=str,
        help='path to store state (GC)',
    )
    add_general_options(parser)
    add_launcher_groups(parser, argv, required=True)
    args = parser.parse_args(argv)

    run_dir = os.path.join(
        args.run_dir,
        'remote-invocation',
        datetime.now().strftime('%Y-%m-%d-%H-%M-%S'),
    )
    init_logging(
        level=args.log_level,
        logfile=os.path.join(run_dir, 'log.txt'),
        color=False,
        extra=False,
    )

    logger.info('Args: %s', vars(args))
    launcher_config = get_launcher_config_from_args(args, run_dir)

    await run(
        launcher_config=launcher_config,
        state_path=args.state_path,
        state_sizes=[readable_to_bytes(x) for x in args.state_sizes],
        repeat=args.repeat,
        run_dir=run_dir,
    )

    return 0
